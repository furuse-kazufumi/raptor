"""SQLite work-graph store — durable system-of-record for endless multi-model work.

One file (`raptor-worklog.db`, WAL mode, local NTFS) is the graph store, the work
queue, the lease broker, and a small append-only audit log. Atomic leasing via
`BEGIN IMMEDIATE` + a conditional `UPDATE ... WHERE status='ready'` makes it safe
for N concurrent heterogeneous worker processes to claim tasks without double
work. Crash-only: killing a worker `-9` mid-work is lossless — the lease expires
and the task returns to `ready` for re-lease. Effects are idempotent so the
mandatory human-restart point is crash-safe.

See docs/superpowers/specs/2026-07-29-graph-orchestration-design.md.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import validate
from .validate import InvariantError

DEFAULT_LEASE_TTL = 900.0  # seconds; a worker must renew or finish within this window
PRUNE_SENTINEL = "⟪ done ⟫ "  # marks a pruned (tombstoned) task spec


def _now() -> float:
    return time.time()


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def new_id() -> str:
    """Sortable-ish id: second-resolution timestamp + random hex for uniqueness."""
    return time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def _loads(text: str | None) -> Any:
    if not text:
        return []
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []


def _content_hash(
    project: str,
    title: str,
    spec: str,
    depends_on: Sequence[str],
    priority: int,
    capability: Sequence[str],
    on_prem_only: bool,
    constraints: Sequence[str],
) -> str:
    payload = _dumps(
        {
            "project": project,
            "title": title,
            "spec": spec,
            "depends_on": sorted(depends_on),
            "priority": priority,
            "capability": sorted(capability),
            "on_prem_only": bool(on_prem_only),
            "constraints": sorted(constraints),
        }
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS task (
    id            TEXT PRIMARY KEY,
    project       TEXT,
    title         TEXT NOT NULL,
    spec          TEXT NOT NULL,
    status        TEXT NOT NULL,
    depends_on    TEXT,            -- JSON array of task ids
    priority      INTEGER NOT NULL DEFAULT 5,
    capability    TEXT,            -- JSON array of tags
    on_prem_only  INTEGER NOT NULL DEFAULT 0,
    lease_owner   TEXT,
    lease_expires REAL,
    attempt       INTEGER NOT NULL DEFAULT 0,
    result_ref    TEXT,
    result_by     TEXT,
    verified_by   TEXT,
    constraints   TEXT,            -- JSON array
    content_hash  TEXT,
    created_at    TEXT,
    updated_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_task_status   ON task(status);
CREATE INDEX IF NOT EXISTS idx_task_priority ON task(priority);

CREATE TABLE IF NOT EXISTS event (
    seq      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       REAL,
    task_id  TEXT,
    kind     TEXT,
    by_model TEXT,
    detail   TEXT
);
CREATE INDEX IF NOT EXISTS idx_event_task ON event(task_id);
"""


class WorkGraph:
    """Durable work-graph over SQLite. Safe for concurrent worker processes."""

    def __init__(self, db_path: str | Path, lease_ttl: float = DEFAULT_LEASE_TTL):
        self.db_path = str(db_path)
        self.lease_ttl = lease_ttl
        self.conn = sqlite3.connect(
            self.db_path, isolation_level=None, timeout=30.0
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA busy_timeout=10000")
        self.conn.executescript(_SCHEMA)

    # ── lifecycle ──────────────────────────────────────────────────────
    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:  # noqa: BLE001
            pass

    def __enter__(self) -> WorkGraph:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── low-level tx helpers ───────────────────────────────────────────
    def _immediate(self):
        """Context-managed BEGIN IMMEDIATE transaction (exclusive write lock)."""
        return _ImmediateTx(self.conn)

    def _emit(self, kind: str, task_id: str, by_model: str | None, detail: Any = None) -> None:
        validate.check_event_kind(kind)
        self.conn.execute(
            "INSERT INTO event(ts, task_id, kind, by_model, detail) VALUES (?,?,?,?,?)",
            (_now(), task_id, kind, by_model or "", _dumps(detail) if detail is not None else None),
        )

    # ── row mapping ────────────────────────────────────────────────────
    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        d = dict(row)
        d["depends_on"] = _loads(d.get("depends_on"))
        d["capability"] = _loads(d.get("capability"))
        d["constraints"] = _loads(d.get("constraints"))
        d["on_prem_only"] = bool(d.get("on_prem_only"))
        return d

    def get(self, task_id: str) -> dict | None:
        return self._row(self.conn.execute("SELECT * FROM task WHERE id=?", (task_id,)).fetchone())

    def all_tasks(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM task ORDER BY priority, created_at").fetchall()
        return [self._row(r) for r in rows]  # type: ignore[misc]

    def deps_map(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for r in self.conn.execute("SELECT id, depends_on FROM task").fetchall():
            out[r["id"]] = list(_loads(r["depends_on"]))
        return out

    def counts(self) -> dict[str, int]:
        out = {s: 0 for s in sorted(validate.STATUS)}
        for r in self.conn.execute("SELECT status, COUNT(*) n FROM task GROUP BY status").fetchall():
            out[r["status"]] = r["n"]
        return out

    def assert_acyclic(self) -> None:
        if validate.has_cycle(self.deps_map()):
            raise InvariantError("work-graph depends_on contains a cycle")

    # ── mutations ──────────────────────────────────────────────────────
    def add_task(
        self,
        *,
        title: str,
        spec: str,
        project: str = "",
        task_id: str | None = None,
        depends_on: Sequence[str] | None = None,
        priority: int = 5,
        capability: Sequence[str] | None = None,
        on_prem_only: bool = False,
        constraints: Sequence[str] | None = None,
    ) -> str:
        """Idempotent upsert of a task node. Returns the task id.

        Re-adding the same id with identical content is a no-op (restart-safe).
        A depends_on edge that would create a cycle is rejected fail-closed.
        Initial status is 'ready' when all deps are already done (or none),
        else 'pending'.
        """
        if not str(title).strip():
            raise InvariantError("title is required")
        if not str(spec).strip():
            raise InvariantError("spec is required (self-contained cold-start text)")
        depends_on = list(depends_on or [])
        capability = validate.check_capabilities(capability or [])
        constraints = list(constraints or [])
        priority = int(priority)
        tid = task_id or new_id()

        chash = _content_hash(
            project, title, spec, depends_on, priority, capability, on_prem_only, constraints
        )

        existing = self.get(tid)
        if existing is not None and existing.get("content_hash") == chash:
            return tid  # idempotent no-op

        # cycle guard: adding these edges must not create a cycle
        deps = self.deps_map()
        deps[tid] = list(depends_on)
        if validate.has_cycle(deps):
            raise InvariantError(
                f"adding task {tid} with depends_on={depends_on} would create a cycle"
            )

        now = _ts()
        with self._immediate():
            if existing is None:
                status = self._initial_status(depends_on)
                self.conn.execute(
                    """INSERT INTO task
                       (id, project, title, spec, status, depends_on, priority, capability,
                        on_prem_only, attempt, constraints, content_hash, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        tid, project, title, spec, status, _dumps(depends_on), priority,
                        _dumps(capability), 1 if on_prem_only else 0, 0,
                        _dumps(constraints), chash, now, now,
                    ),
                )
                self._emit("created", tid, None, {"status": status, "project": project})
                if status == "ready":
                    self._emit("ready", tid, None)
            else:
                # content changed → update definition, keep runtime state unless
                # deps change re-opens readiness.
                self.conn.execute(
                    """UPDATE task SET project=?, title=?, spec=?, depends_on=?, priority=?,
                          capability=?, on_prem_only=?, constraints=?, content_hash=?, updated_at=?
                       WHERE id=?""",
                    (
                        project, title, spec, _dumps(depends_on), priority, _dumps(capability),
                        1 if on_prem_only else 0, _dumps(constraints), chash, now, tid,
                    ),
                )
                self._emit("created", tid, None, {"updated": True})
        # recompute readiness (a changed/added task may now be ready or block)
        self.recompute_ready()
        return tid

    def _initial_status(self, depends_on: Sequence[str]) -> str:
        if not depends_on:
            return "ready"
        # ready iff every existing dep is done; unknown deps keep it pending
        placeholders = ",".join("?" for _ in depends_on)
        rows = self.conn.execute(
            f"SELECT id, status FROM task WHERE id IN ({placeholders})", tuple(depends_on)
        ).fetchall()
        by_id = {r["id"]: r["status"] for r in rows}
        for d in depends_on:
            if by_id.get(d) != "done":
                return "pending"
        return "ready"

    def add_dep(self, task_id: str, dep_id: str) -> None:
        """Add a depends_on edge, fail-closed on cycle."""
        t = self.get(task_id)
        if t is None:
            raise InvariantError(f"unknown task: {task_id}")
        deps = self.deps_map()
        if validate.would_create_cycle(deps, task_id, dep_id):
            raise InvariantError(f"edge {task_id} -> {dep_id} would create a cycle")
        new_deps = list(dict.fromkeys([*t["depends_on"], dep_id]))
        with self._immediate():
            self.conn.execute(
                "UPDATE task SET depends_on=?, updated_at=? WHERE id=?",
                (_dumps(new_deps), _ts(), task_id),
            )
        self.recompute_ready()

    def recompute_ready(self) -> int:
        """Reconcile a task's status with its dependency states, in BOTH directions:
        pending/blocked→ready when all deps are done; any→blocked when a dep failed;
        and — the demotion the old code missed — a still-runnable 'ready' task back to
        'pending' (or 'blocked') when a newly-added / newly-un-done dependency means it
        must NOT run yet. Scanning 'ready' too closes the gating hole where add_dep()
        (or a dependency that fails) left a task leaseable ahead of an unmet dependency.
        Never touches leased/done/failed rows. Returns the number of tasks changed."""
        changed = 0
        rows = self.conn.execute(
            "SELECT id, status, depends_on FROM task WHERE status IN ('pending','blocked','ready')"
        ).fetchall()
        status_by_id = {
            r["id"]: r["status"]
            for r in self.conn.execute("SELECT id, status FROM task").fetchall()
        }
        for r in rows:
            deps = _loads(r["depends_on"])
            dep_states = [status_by_id.get(d) for d in deps]
            if any(s == "failed" for s in dep_states):
                if r["status"] != "blocked":
                    with self._immediate():
                        n = self.conn.execute(
                            "UPDATE task SET status='blocked', updated_at=? WHERE id=? AND status IN ('pending','ready')",
                            (_ts(), r["id"]),
                        ).rowcount
                        if n:
                            self._emit("blocked", r["id"], None, {"reason": "dependency failed"})
                    if n:
                        changed += 1
                continue
            if all(s == "done" for s in dep_states):
                with self._immediate():
                    n = self.conn.execute(
                        "UPDATE task SET status='ready', updated_at=? WHERE id=? AND status IN ('pending','blocked')",
                        (_ts(), r["id"]),
                    ).rowcount
                    if n:
                        self._emit("ready", r["id"], None)
                if n:
                    changed += 1
            elif r["status"] == "ready":
                # A dependency is not yet done (and none failed): demote so the task
                # cannot be leased ahead of it. This is the missing 'ready'->'pending'.
                with self._immediate():
                    n = self.conn.execute(
                        "UPDATE task SET status='pending', updated_at=? WHERE id=? AND status='ready'",
                        (_ts(), r["id"]),
                    ).rowcount
                    if n:
                        self._emit("pending", r["id"], None, {"reason": "dependency unmet"})
                if n:
                    changed += 1
        return changed

    # ── leasing (atomic) ───────────────────────────────────────────────
    def _candidate_query(self, model: str, capability: str | None) -> tuple[str, tuple]:
        is_cloud = not validate.is_local_model(model)
        clauses = ["status='ready'"]
        params: list[Any] = []
        if is_cloud:
            clauses.append("on_prem_only=0")  # cloud model cannot take on-prem-only work
        sql = (
            "SELECT * FROM task WHERE " + " AND ".join(clauses) +
            " ORDER BY priority ASC, created_at ASC"
        )
        return sql, tuple(params)

    def lease_next(
        self,
        owner: str,
        model: str,
        ttl: float | None = None,
        capability: str | None = None,
    ) -> dict | None:
        """Atomically lease the top ready task this worker may run. Returns the
        leased task dict, or None if nothing is runnable for this worker.

        `capability`, when given, restricts to tasks tagged with it (the routing
        layer decides which capability a given model claims)."""
        ttl = self.lease_ttl if ttl is None else ttl
        sql, params = self._candidate_query(model, capability)
        with self._immediate():
            for row in self.conn.execute(sql, params).fetchall():
                task = self._row(row)
                assert task is not None
                if capability and capability not in task["capability"]:
                    continue
                expires = _now() + ttl
                n = self.conn.execute(
                    "UPDATE task SET status='leased', lease_owner=?, lease_expires=?, "
                    "attempt=attempt+1, updated_at=? WHERE id=? AND status='ready'",
                    (owner, expires, _ts(), task["id"]),
                ).rowcount
                if n == 1:
                    self._emit("leased", task["id"], model, {"owner": owner, "ttl": ttl})
                    return self.get(task["id"])
            return None

    def lease(self, task_id: str, owner: str, model: str, ttl: float | None = None) -> dict | None:
        """Atomically lease one specific task by id (for CLI/tests)."""
        ttl = self.lease_ttl if ttl is None else ttl
        with self._immediate():
            t = self.get(task_id)
            if t is None:
                raise InvariantError(f"unknown task: {task_id}")
            if t["on_prem_only"] and not validate.is_local_model(model):
                raise InvariantError(f"on_prem_only task {task_id} cannot be leased by cloud model {model}")
            expires = _now() + ttl
            n = self.conn.execute(
                "UPDATE task SET status='leased', lease_owner=?, lease_expires=?, "
                "attempt=attempt+1, updated_at=? WHERE id=? AND status='ready'",
                (owner, expires, _ts(), task_id),
            ).rowcount
            if n == 1:
                self._emit("leased", task_id, model, {"owner": owner})
                return self.get(task_id)
        return None

    def renew_lease(self, task_id: str, owner: str, ttl: float | None = None) -> bool:
        """Heartbeat: extend the lease if this worker still owns it."""
        ttl = self.lease_ttl if ttl is None else ttl
        with self._immediate():
            n = self.conn.execute(
                "UPDATE task SET lease_expires=?, updated_at=? "
                "WHERE id=? AND status='leased' AND lease_owner=?",
                (_now() + ttl, _ts(), task_id, owner),
            ).rowcount
        return n == 1

    def reclaim_expired(self, now: float | None = None) -> int:
        """Return timed-out leases to 'ready' (crash recovery). Returns count."""
        now = _now() if now is None else now
        with self._immediate():
            rows = self.conn.execute(
                "SELECT id FROM task WHERE status='leased' AND lease_expires IS NOT NULL AND lease_expires < ?",
                (now,),
            ).fetchall()
            for r in rows:
                self.conn.execute(
                    "UPDATE task SET status='ready', lease_owner=NULL, lease_expires=NULL, updated_at=? WHERE id=?",
                    (_ts(), r["id"]),
                )
                self._emit("lease_expired", r["id"], None)
        return len(rows)

    def release(self, task_id: str, owner: str) -> bool:
        """Return a leased task to 'ready' without counting a failure (e.g. a
        human-gated task the autonomous driver may not run). No-op unless this
        worker still owns the lease."""
        with self._immediate():
            n = self.conn.execute(
                "UPDATE task SET status='ready', lease_owner=NULL, lease_expires=NULL, updated_at=? "
                "WHERE id=? AND status='leased' AND lease_owner=?",
                (_ts(), task_id, owner),
            ).rowcount
            if n:
                self._emit("lease_expired", task_id, None, {"released": True})
        return n == 1

    # ── completion ─────────────────────────────────────────────────────
    def complete(
        self,
        task_id: str,
        owner: str,
        result_ref: str,
        result_by: str,
        verified_by: str | None = None,
        verifier_model: str | None = None,
        strict_verify: bool = False,
    ) -> dict:
        """Mark a leased task done. Fails fail-closed on a stale lease or a
        violated verify gate. Unblocks dependents afterward."""
        with self._immediate():
            t = self.get(task_id)
            if t is None:
                raise InvariantError(f"unknown task: {task_id}")
            if t["status"] != "leased" or t["lease_owner"] != owner:
                raise InvariantError(
                    f"stale lease: task {task_id} is {t['status']} owned by {t['lease_owner']!r}, not {owner!r}"
                )
            if strict_verify:
                if not verified_by:
                    raise InvariantError(f"verify gate: task {task_id} needs a different-provider verified_by")
                if validate.provider_of(verifier_model) == validate.provider_of(result_by):
                    raise InvariantError(
                        f"verify gate: verifier provider must differ from author "
                        f"({validate.provider_of(result_by)})"
                    )
            self.conn.execute(
                "UPDATE task SET status='done', result_ref=?, result_by=?, verified_by=?, "
                "lease_owner=NULL, lease_expires=NULL, updated_at=? WHERE id=?",
                (result_ref, result_by, verified_by, _ts(), task_id),
            )
            self._emit("done", task_id, result_by, {"result_ref": result_ref, "verified_by": verified_by})
        self.recompute_ready()
        result = self.get(task_id)
        assert result is not None
        return result

    def fail(self, task_id: str, owner: str | None, reason: str) -> dict:
        """Mark a task failed (releases its lease). Blocks dependents."""
        with self._immediate():
            t = self.get(task_id)
            if t is None:
                raise InvariantError(f"unknown task: {task_id}")
            self.conn.execute(
                "UPDATE task SET status='failed', lease_owner=NULL, lease_expires=NULL, updated_at=? WHERE id=?",
                (_ts(), task_id),
            )
            self._emit("failed", task_id, None, {"owner": owner, "reason": reason})
        self.recompute_ready()
        result = self.get(task_id)
        assert result is not None
        return result

    def mark_verified(self, task_id: str, verified_by: str) -> None:
        with self._immediate():
            self.conn.execute(
                "UPDATE task SET verified_by=?, updated_at=? WHERE id=?",
                (verified_by, _ts(), task_id),
            )
            self._emit("verified", task_id, None, {"verified_by": verified_by})

    # ── scheduling views ───────────────────────────────────────────────
    def ready_set(self, model: str | None = None, capability: str | None = None) -> list[dict]:
        """Tasks runnable right now, ordered by priority then age. If `model` is
        a cloud model, on_prem_only tasks are excluded."""
        rows = self.conn.execute(
            "SELECT * FROM task WHERE status='ready' ORDER BY priority ASC, created_at ASC"
        ).fetchall()
        out = []
        for r in rows:
            t = self._row(r)
            assert t is not None
            if model and not validate.is_local_model(model) and t["on_prem_only"]:
                continue
            if capability and capability not in t["capability"]:
                continue
            out.append(t)
        return out

    # ── audit / events ─────────────────────────────────────────────────
    def events(self, limit: int | None = None) -> list[dict]:
        sql = "SELECT * FROM event ORDER BY seq"
        if limit:
            sql += f" DESC LIMIT {int(limit)}"
        rows = self.conn.execute(sql).fetchall()
        result = [dict(r) for r in rows]
        if limit:
            result.reverse()
        return result

    def export_events_jsonl(self, path: str | Path) -> int:
        rows = self.conn.execute("SELECT * FROM event ORDER BY seq").fetchall()
        p = Path(path)
        with p.open("w", encoding="utf-8") as fh:
            for r in rows:
                d = dict(r)
                if d.get("detail"):
                    d["detail"] = _loads(d["detail"])
                fh.write(json.dumps(d, ensure_ascii=False) + "\n")
        return len(rows)

    # ── retention / pruning (bounded memory) ──────────────────────────
    def prune_done(
        self,
        older_than_seconds: float,
        now: float | None = None,
        summarizer=None,
    ) -> int:
        """Trim finished tasks to a bounded tombstone once they age past the
        retention window. A completed task does not need its full ~10 KB `spec`
        remembered — only the *fact* it finished, kept for a period. Replaces the
        heavy `spec` with a short marker (optionally a bounded 1-line summary via
        `summarizer(old_spec) -> str`), keeping id/title/status/timestamps/
        result_ref. Idempotent (already-pruned rows are skipped). Returns count."""
        now = _now() if now is None else now
        cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now - older_than_seconds))
        rows = self.conn.execute(
            "SELECT id, title, spec, updated_at FROM task "
            "WHERE status='done' AND updated_at < ? AND spec NOT LIKE ?",
            (cutoff, PRUNE_SENTINEL + "%"),
        ).fetchall()
        pruned = 0
        for r in rows:
            summary = ""
            if summarizer is not None:
                try:
                    summary = str(summarizer(r["spec"]) or "").strip().replace("\n", " ")
                except Exception:  # noqa: BLE001
                    summary = ""
            tomb = f"{PRUNE_SENTINEL}{r['title']} (done {r['updated_at']}; detail pruned)"
            if summary:
                tomb += f" — {summary}"
            with self._immediate():
                self.conn.execute(
                    "UPDATE task SET spec=?, updated_at=? WHERE id=?",
                    (tomb, _ts(), r["id"]),
                )
            pruned += 1
        return pruned

    # ── escalation signals (F5: defend against endless-idle) ───────────
    def escalation(self) -> dict:
        """Signals the driver escalates to a human. Runnable work existing while
        the ready-set is empty (all blocked/leased/pending-with-unmet-deps) is the
        real endless-loop failure mode — a driver alive and doing nothing."""
        c = self.counts()
        open_work = c["pending"] + c["ready"] + c["leased"] + c["blocked"]
        runnable_now = c["ready"] + c["leased"]
        double_failed = [
            r["id"]
            for r in self.conn.execute(
                "SELECT id FROM task WHERE status='failed' AND attempt>=2"
            ).fetchall()
        ]
        return {
            "open_work": open_work,
            "ready": c["ready"],
            "leased": c["leased"],
            "blocked": c["blocked"],
            "pending": c["pending"],
            # work remains but nothing can run and nothing is running:
            "stalled": open_work > 0 and runnable_now == 0,
            "double_failed": double_failed,
        }


class _ImmediateTx:
    """`with wg._immediate():` → BEGIN IMMEDIATE / COMMIT (ROLLBACK on error)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self):
        self.conn.execute("BEGIN IMMEDIATE")
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.execute("COMMIT")
        else:
            try:
                self.conn.execute("ROLLBACK")
            except Exception:  # noqa: BLE001
                pass
        return False


def open_graph(db_path: str | Path | None = None, lease_ttl: float = DEFAULT_LEASE_TTL) -> WorkGraph:
    """Open (creating if needed) the work-graph at db_path (default: raptor dir)."""
    if db_path is None:
        db_path = Path(__file__).resolve().parents[2] / "raptor-worklog.db"
    return WorkGraph(db_path, lease_ttl=lease_ttl)

"""External driver — the supervisor loop that makes work "endless".

This is the honest home of "endless": the model cannot restart itself, so a
process *outside* the model does. Each tick the driver reclaims expired leases,
recomputes readiness, picks the top runnable task, routes it to a worker
(local-first), leases it, runs it, and commits the result back to the graph.

Two honest boundaries (spec §2):
- It runs only **autonomous** workers (Ollama local, Codex headless). Tasks that
  route to Claude are **human-gated** — surfaced, never auto-run.
- It **escalates to a human** when work exists but nothing is runnable (the real
  endless-idle failure mode) and **halts at an auth gate** — never loops past
  a re-login prompt.

`serve()` is what `rp -Serve` invokes; `run_once()` is one tick (unit-testable).
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path

from . import routing, validate, workers
from .store import WorkGraph, new_id, open_graph

_AUTH_HINTS = ("re-login", "relogin", "unauthorized", "not logged in", "login required", "401")
_LIMIT_HINTS = (
    "rate limit", "rate-limit", "ratelimit", "quota", "exceeded", "429",
    "too many requests", "usage limit", "insufficient", "overloaded", "capacity",
    "session limit", "context limit", "out of tokens",
)


# margin on top of a command's own timeout: artifact copy + the commit write
_TOOL_LEASE_MARGIN = 120.0


def _lease_ttl_for(task: dict, model: str) -> float | None:
    """Lease TTL for one task, or None to use the graph default.

    A deterministic command may legitimately occupy its whole `timeout` — a
    render is seconds, a NAS sweep is hours — which outlives the default lease
    TTL. That matters because an expired lease is reclaimed to 'ready' and can be
    leased again *while the first command is still running*, i.e. a second
    concurrent run of the same heavy job (and the first one's `complete()` then
    fails on a stale lease, silently discarding finished work). So derive the TTL
    from the bound the task itself declares.
    """
    if not model.startswith("tool:"):
        return None
    try:
        timeout = float(json.loads(task["spec"]).get("timeout", 900))
    except Exception:  # noqa: BLE001  (non-JSON spec — the worker will reject it)
        return None
    return timeout + _TOOL_LEASE_MARGIN


def _looks_like_auth(err: str | None) -> bool:
    if not err:
        return False
    e = err.lower()
    return any(h in e for h in _AUTH_HINTS)


def _looks_like_limit(err: str | None) -> bool:
    """A transient budget/rate/session-limit signal — route around it, don't fail
    the task. This is the crux of 'develop without stopping at session limits':
    a rate-limited worker cools down while local/other workers keep going."""
    if not err:
        return False
    e = err.lower()
    return any(h in e for h in _LIMIT_HINTS)


_VERIFY_PROMPT = (
    "You are an independent verifier (a DIFFERENT provider than the author). Given a TASK and "
    "the RESULT produced for it, judge whether the result correctly and completely satisfies the "
    "task. Reply on the FIRST line with exactly PASS or FAIL, then a one-line reason.\n\n"
)


def _verdict_passed(text: str) -> bool:
    lines = (text or "").strip().splitlines()
    if not lines:
        return False
    return lines[0].strip().upper().startswith("PASS")


def _pick_verifier(available: list[str], author_provider: str) -> str | None:
    """A verifier from a different provider than the author (two-pillar gate).
    Prefers headless read-only providers."""
    for m in ("codex", "copilot"):
        if m in available and validate.provider_of(m) != author_provider:
            return m
    return None


def run_once(
    wg: WorkGraph,
    artifacts_dir: str | Path,
    available: list[str] | None = None,
    prefer_local: bool = True,
    allow_human_gated: bool = False,
    verify: bool = False,
    exclude_models: set[str] | None = None,
) -> dict:
    """One scheduler tick. Returns an outcome dict with an `action`:
    completed | failed | needs_human | idle | stalled | auth_halt | rate_limited.
    `exclude_models` skips models under a rate-limit cooldown (route-around).
    `verify=True` runs a different-provider verifier on a successful autonomous
    result before marking it done (the two-pillar gate); a FAIL verdict surfaces
    the task to a human instead of auto-completing."""
    artifacts_dir = Path(artifacts_dir)
    wg.reclaim_expired()
    wg.recompute_ready()

    esc = wg.escalation()
    if esc["stalled"]:
        return {"action": "stalled", **{k: esc[k] for k in ("open_work", "blocked", "pending")}}
    if esc["double_failed"]:
        return {"action": "needs_human", "reason": "double_failed", "tasks": esc["double_failed"]}

    available = list(available if available is not None else workers.available_models())
    if exclude_models:
        available = [m for m in available if m not in exclude_models]
    pending_human: tuple[dict, str] | None = None

    for t in wg.ready_set():
        model = routing.route(t["capability"], t["on_prem_only"], available, prefer_local)
        if model is None:
            continue  # nothing available can serve this task right now
        worker = workers.make_worker(model)
        if not worker.autonomous and not allow_human_gated:
            if pending_human is None:
                pending_human = (t, model)
            continue

        owner = "sess-" + new_id()
        leased = wg.lease(t["id"], owner=owner, model=model, ttl=_lease_ttl_for(t, model))
        if leased is None:
            continue  # a concurrent worker claimed it first

        res = worker.run(leased, artifacts_dir)

        if res.needs_human:
            wg.release(leased["id"], owner)
            if pending_human is None:
                pending_human = (leased, model)
            continue
        if res.ok:
            verified_by = None
            verifier_model = None
            # Deterministic tools are self-verifying: the worker fails closed when
            # the declared artifact is missing, and the result is a file (often
            # binary), not a claim an LLM can review. Sending a render's JSON spec
            # to a verifier only risks a bogus FAIL that halts autonomous progress.
            if verify and not model.startswith("tool:"):
                vmodel = _pick_verifier(available, validate.provider_of(model))
                if vmodel:
                    vtask = {
                        **leased,
                        "spec": _VERIFY_PROMPT + "=== TASK ===\n" + leased["spec"][:4000]
                        + "\n\n=== RESULT ===\n" + (res.output or "")[:4000],
                    }
                    vres = workers.make_worker(vmodel).run(vtask, artifacts_dir)
                    if vres.ok and _verdict_passed(vres.output):
                        verified_by = "sess-" + new_id()
                        verifier_model = vmodel
                    elif vres.ok:
                        # verifier ran and returned FAIL → do not auto-complete
                        wg.release(leased["id"], owner)
                        return {"action": "needs_human", "task_id": leased["id"], "model": model,
                                "reason": "verify_failed", "verifier": vmodel}
                    # verifier errored/unavailable → fall through to a lenient complete
            wg.complete(
                leased["id"], owner=owner, result_ref=res.result_ref or "",
                result_by=model, verified_by=verified_by, verifier_model=verifier_model,
                strict_verify=bool(verify and verified_by),
            )
            return {
                "action": "completed", "task_id": leased["id"], "model": model,
                "result_ref": res.result_ref, "duration": round(res.duration, 2),
                "verified_by": verified_by, "verifier": verifier_model,
            }
        # failure
        if _looks_like_auth(res.error):
            wg.release(leased["id"], owner)
            return {"action": "auth_halt", "task_id": leased["id"], "model": model, "error": res.error}
        if _looks_like_limit(res.error):
            # session/rate/budget limit → hand the task back to the graph (release,
            # not fail) so another model or a fresh invocation resumes it.
            wg.release(leased["id"], owner)
            return {"action": "rate_limited", "task_id": leased["id"], "model": model, "error": res.error}
        wg.fail(leased["id"], owner=owner, reason=res.error or "worker failed")
        return {"action": "failed", "task_id": leased["id"], "model": model, "error": res.error}

    if pending_human is not None:
        t, model = pending_human
        return {"action": "needs_human", "task_id": t["id"], "model": model,
                "reason": "human_gated", "project": t.get("project", "")}
    return {"action": "idle"}


def serve(
    wg: WorkGraph,
    artifacts_dir: str | Path,
    max_ticks: int | None = None,
    poll_interval: float = 5.0,
    prefer_local: bool = True,
    allow_human_gated: bool = False,
    verify: bool = False,
    idle_escalate_after: int | None = 3,
    cooldown_seconds: float = 300.0,
    watch: bool = False,
    on_event: Callable[[dict], None] = lambda e: None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.time,
) -> dict:
    """Drain all runnable autonomous work, then exit cleanly — the exit point IS
    the handoff (durable state is in the graph; a fresh cold invocation resumes,
    and model reload is cheap, so no resident daemon is needed).

    `watch=True` is the PoC/debug resident mode: it does NOT exit on idle — it keeps
    polling and emits a heartbeat (graph counts) each idle tick so you can monitor and
    debug live. It still halts at the auth gate and honors max_ticks; stop it with
    Ctrl-C. Use the drain-then-exit default for production handoff.

    Stops on: auth_halt (human), stalled (escalate), max_ticks, or
    idle_escalate_after consecutive no-progress ticks. A rate-limited model is put
    on a cooldown and routed around (other models / a later invocation resume its
    task) — that is how work continues past a single worker's session/budget limit.
    `sleep`/`clock`/`on_event` are injectable for tests."""
    tick = 0
    idle_ticks = 0
    completed = 0
    failed = 0
    rate_limited = 0
    cooldown: dict[str, float] = {}
    last: dict = {"action": "idle"}
    while True:
        tick += 1
        excluded = {m for m, until in cooldown.items() if until > clock()}
        out = run_once(
            wg, artifacts_dir, prefer_local=prefer_local,
            allow_human_gated=allow_human_gated, verify=verify,
            exclude_models=excluded,
        )
        last = out
        on_event(out)
        action = out["action"]

        if action == "auth_halt":
            break  # honest: never loop past the auth gate
        if action == "stalled":
            wg._emit("escalated", out.get("task_id", ""), None, {"reason": "stalled"})
            break
        if action == "completed":
            completed += 1
            idle_ticks = 0
        elif action == "failed":
            failed += 1
            idle_ticks = 0
        elif action == "rate_limited":
            rate_limited += 1
            idle_ticks = 0
            cooldown[out["model"]] = clock() + cooldown_seconds  # route around this model
        else:  # idle | needs_human → no autonomous progress this tick
            idle_ticks += 1

        if max_ticks is not None and tick >= max_ticks:
            break
        # watch (PoC/debug) mode never exits on idle — it stays resident to monitor
        if not watch and idle_escalate_after is not None and idle_ticks >= idle_escalate_after:
            wg._emit("escalated", out.get("task_id", ""), None,
                     {"reason": action, "idle_ticks": idle_ticks})
            break  # clean handoff: nothing autonomous left; a fresh session/human resumes
        if action in ("idle", "needs_human", "rate_limited"):
            if watch:
                on_event({"action": "watch", "tick": tick, "counts": wg.counts()})
            sleep(poll_interval)

    counts = wg.counts()
    return {
        "ticks": tick, "completed": completed, "failed": failed, "rate_limited": rate_limited,
        "handoff": {
            "ready_remaining": counts["ready"], "leased": counts["leased"],
            "blocked": counts["blocked"], "done": counts["done"], "failed": counts["failed"],
        },
        "last": last,
    }


def _worker_loop(db_path, artifacts_dir, worker_id: str, results: dict, on_event, lock, **serve_kwargs) -> None:
    """One worker thread: its OWN WorkGraph connection (sqlite is per-thread),
    coordinating with peers purely through the atomic lease (blackboard)."""
    wg = open_graph(db_path)
    try:
        def emit(e):
            with lock:
                on_event({**e, "worker": worker_id})
        results[worker_id] = serve(wg, artifacts_dir, on_event=emit, **serve_kwargs)
    finally:
        wg.close()


def parallel_serve(
    db_path,
    artifacts_dir,
    n_workers: int = 3,
    max_ticks: int | None = None,
    poll_interval: float = 5.0,
    prefer_local: bool = True,
    allow_human_gated: bool = False,
    verify: bool = False,
    idle_escalate_after: int | None = 3,
    on_event: Callable[[dict], None] = lambda e: None,
) -> dict:
    """Run N concurrent worker threads against one work-graph. This is what
    "3+ models working at once" means: each worker leases a different ready task
    (atomic lease guarantees no double-processing), so capability-diverse tasks
    fan out to different models simultaneously — using more of the machine's
    memory/compute. Coordination is stigmergic (only through the graph)."""
    results: dict = {}
    lock = threading.Lock()
    threads = []
    sk = {
        "max_ticks": max_ticks, "poll_interval": poll_interval, "prefer_local": prefer_local,
        "allow_human_gated": allow_human_gated, "verify": verify,
        "idle_escalate_after": idle_escalate_after,
    }
    for i in range(n_workers):
        t = threading.Thread(
            target=_worker_loop,
            args=(db_path, artifacts_dir, f"w{i}", results, on_event, lock),
            kwargs=sk, daemon=True,
        )
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    return {
        "workers": n_workers,
        "completed": sum(r.get("completed", 0) for r in results.values()),
        "failed": sum(r.get("failed", 0) for r in results.values()),
        "rate_limited": sum(r.get("rate_limited", 0) for r in results.values()),
        "per_worker": results,
    }

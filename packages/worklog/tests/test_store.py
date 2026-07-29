"""Work-graph store tests: leasing atomicity, idempotency, ready-set, cycle
rejection, TTL reclaim, verify gate, on-prem routing, escalation."""

import time

import pytest

from packages.worklog import store as store_mod
from packages.worklog.store import WorkGraph
from packages.worklog.validate import InvariantError


@pytest.fixture()
def wg(tmp_path):
    g = WorkGraph(tmp_path / "wg.db", lease_ttl=900.0)
    try:
        yield g
    finally:
        g.close()


def test_add_task_ready_when_no_deps(wg):
    tid = wg.add_task(title="t1", spec="do the thing", project="p")
    t = wg.get(tid)
    assert t["status"] == "ready"
    assert t["title"] == "t1"
    assert t["project"] == "p"


def test_add_task_idempotent(wg):
    tid = wg.add_task(title="t1", spec="s", task_id="fixed")
    again = wg.add_task(title="t1", spec="s", task_id="fixed")
    assert again == tid == "fixed"
    assert len(wg.all_tasks()) == 1
    created = [e for e in wg.events() if e["kind"] == "created"]
    assert len(created) == 1  # no duplicate creation event on identical re-add


def test_deps_keep_pending_until_done(wg):
    wg.add_task(title="a", spec="s", task_id="a")
    b = wg.add_task(title="b", spec="s", task_id="b", depends_on=["a"])
    assert wg.get(b)["status"] == "pending"
    # lease + complete a
    wg.lease("a", owner="w1", model="ollama:x")
    wg.complete("a", owner="w1", result_ref="out/a.txt", result_by="ollama:x")
    assert wg.get(b)["status"] == "ready"


def test_cycle_rejected_fail_closed(wg):
    wg.add_task(title="a", spec="s", task_id="a")
    wg.add_task(title="b", spec="s", task_id="b", depends_on=["a"])
    with pytest.raises(InvariantError):
        # b already depends on a; making a depend on b closes the cycle
        wg.add_dep("a", "b")


def test_lease_is_exclusive(wg):
    wg.add_task(title="a", spec="s", task_id="a")
    first = wg.lease_next(owner="w1", model="ollama:x")
    assert first is not None and first["id"] == "a"
    assert first["status"] == "leased" and first["lease_owner"] == "w1"
    # nothing left to lease
    second = wg.lease_next(owner="w2", model="ollama:x")
    assert second is None


def test_complete_requires_owning_lease(wg):
    wg.add_task(title="a", spec="s", task_id="a")
    wg.lease("a", owner="w1", model="ollama:x")
    with pytest.raises(InvariantError):
        wg.complete("a", owner="w2", result_ref="r", result_by="ollama:x")  # stale/foreign lease
    done = wg.complete("a", owner="w1", result_ref="r", result_by="ollama:x")
    assert done["status"] == "done"
    assert done["result_ref"] == "r"


def test_reclaim_expired_lease(wg):
    wg.add_task(title="a", spec="s", task_id="a")
    wg.lease("a", owner="w1", model="ollama:x", ttl=1.0)
    assert wg.get("a")["status"] == "leased"
    # force expiry by asking reclaim with a far-future 'now'
    n = wg.reclaim_expired(now=time.time() + 10_000)
    assert n == 1
    assert wg.get("a")["status"] == "ready"
    assert wg.get("a")["lease_owner"] is None


def test_on_prem_only_excludes_cloud_model(wg):
    wg.add_task(title="secret", spec="s", task_id="a", on_prem_only=True)
    # cloud model cannot lease it via lease_next
    assert wg.lease_next(owner="c", model="claude") is None
    # explicit lease by cloud model is rejected fail-closed
    with pytest.raises(InvariantError):
        wg.lease("a", owner="c", model="claude")
    # local model can
    got = wg.lease_next(owner="l", model="ollama:qwen2.5:14b")
    assert got is not None and got["id"] == "a"


def test_verify_gate_strict(wg):
    wg.add_task(title="a", spec="s", task_id="a")
    wg.lease("a", owner="w1", model="ollama:x")
    # strict: no verifier → reject
    with pytest.raises(InvariantError):
        wg.complete("a", owner="w1", result_ref="r", result_by="claude", strict_verify=True)
    # strict: same-provider verifier → reject
    with pytest.raises(InvariantError):
        wg.complete(
            "a", owner="w1", result_ref="r", result_by="claude",
            verified_by="sess2", verifier_model="claude", strict_verify=True,
        )
    # strict: different-provider verifier → ok
    done = wg.complete(
        "a", owner="w1", result_ref="r", result_by="claude",
        verified_by="sess2", verifier_model="codex", strict_verify=True,
    )
    assert done["status"] == "done"
    assert done["verified_by"] == "sess2"


def test_fail_blocks_dependents(wg):
    wg.add_task(title="a", spec="s", task_id="a")
    wg.add_task(title="b", spec="s", task_id="b", depends_on=["a"])
    wg.lease("a", owner="w1", model="ollama:x")
    wg.fail("a", owner="w1", reason="boom")
    assert wg.get("a")["status"] == "failed"
    assert wg.get("b")["status"] == "blocked"


def test_ready_set_priority_order(wg):
    wg.add_task(title="low", spec="s", task_id="low", priority=9)
    wg.add_task(title="high", spec="s", task_id="high", priority=1)
    wg.add_task(title="mid", spec="s", task_id="mid", priority=5)
    order = [t["id"] for t in wg.ready_set()]
    assert order == ["high", "mid", "low"]


def test_escalation_stalled(wg):
    wg.add_task(title="a", spec="s", task_id="a")
    wg.add_task(title="b", spec="s", task_id="b", depends_on=["a"])
    wg.lease("a", owner="w1", model="ollama:x")
    wg.fail("a", owner="w1", reason="boom")  # a failed, b blocked, nothing ready/leased
    esc = wg.escalation()
    assert esc["stalled"] is True
    assert esc["open_work"] >= 1


def test_export_events_jsonl(wg, tmp_path):
    wg.add_task(title="a", spec="s", task_id="a")
    wg.lease("a", owner="w1", model="ollama:x")
    wg.complete("a", owner="w1", result_ref="r", result_by="ollama:x")
    out = tmp_path / "events.jsonl"
    n = wg.export_events_jsonl(out)
    assert n >= 3
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    kinds = [__import__("json").loads(ln)["kind"] for ln in lines]
    assert "created" in kinds and "leased" in kinds and "done" in kinds


def test_prune_done_tombstones_old_tasks(wg):
    wg.add_task(task_id="a", title="taskA", spec="X" * 5000)
    wg.lease("a", owner="w", model="ollama:x")
    wg.complete("a", owner="w", result_ref="r", result_by="ollama:x")
    # prune finished tasks (treat 'now' as far in the future so it's past retention)
    n = wg.prune_done(older_than_seconds=0, now=time.time() + 10_000)
    assert n == 1
    t = wg.get("a")
    assert t["status"] == "done"          # the FACT it finished is preserved
    assert "detail pruned" in t["spec"]   # heavy ~5 KB spec dropped
    assert len(t["spec"]) < 200           # bounded tombstone
    # idempotent — a second prune is a no-op (already tombstoned)
    assert wg.prune_done(0, now=time.time() + 10_000) == 0


def test_new_id_unique():
    ids = {store_mod.new_id() for _ in range(200)}
    assert len(ids) == 200

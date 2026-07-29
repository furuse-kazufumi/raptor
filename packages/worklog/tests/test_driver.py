"""Driver tests — one-tick scheduling, human-gating, kill-and-resume, escalation.

Ollama is stubbed at the subprocess boundary so no real model runs; the full
lease -> run -> commit path is exercised."""

import time

import pytest

from packages.worklog import driver, workers
from packages.worklog.store import WorkGraph


@pytest.fixture()
def wg(tmp_path):
    g = WorkGraph(tmp_path / "wg.db", lease_ttl=900.0)
    try:
        yield g
    finally:
        g.close()


@pytest.fixture()
def stub_ollama(monkeypatch):
    """Make OllamaWorker succeed without a real model."""
    class _P:
        returncode = 0
        stdout = "stub deliverable"
        stderr = ""

    monkeypatch.setattr(workers.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(workers.subprocess, "run", lambda *a, **k: _P())


def test_run_once_completes_autonomous_task(wg, tmp_path, stub_ollama):
    wg.add_task(task_id="s1", title="sum", spec="summarize this", capability=["summarize"])
    out = driver.run_once(wg, tmp_path / "artifacts", available=["ollama:qwen2.5:14b", "tool:deterministic"])
    assert out["action"] == "completed"
    assert out["task_id"] == "s1"
    assert wg.get("s1")["status"] == "done"
    assert wg.get("s1")["result_ref"]


def test_run_once_human_gates_reason_task(wg, tmp_path):
    wg.add_task(task_id="r1", title="reason", spec="hard reasoning", capability=["reason"])
    out = driver.run_once(wg, tmp_path / "artifacts", available=["claude", "tool:deterministic"])
    assert out["action"] == "needs_human"
    assert out["task_id"] == "r1"
    # released back to ready — not stuck leased
    assert wg.get("r1")["status"] == "ready"


def test_run_once_idle_when_no_tasks(wg, tmp_path):
    out = driver.run_once(wg, tmp_path / "artifacts", available=["ollama:qwen2.5:14b"])
    assert out["action"] == "idle"


def test_run_once_stalled_on_failed_dependency(wg, tmp_path, stub_ollama):
    wg.add_task(task_id="a", title="a", spec="s", capability=["summarize"])
    wg.add_task(task_id="b", title="b", spec="s", capability=["summarize"], depends_on=["a"])
    wg.lease("a", owner="w1", model="ollama:x")
    wg.fail("a", owner="w1", reason="boom")  # a failed, b blocked → nothing runnable
    out = driver.run_once(wg, tmp_path / "artifacts", available=["ollama:qwen2.5:14b"])
    assert out["action"] == "stalled"


def test_kill_and_resume(wg, tmp_path, stub_ollama):
    """The headline proof: a worker 'crashes' mid-task (lease held, never
    completed); a later tick reclaims the expired lease and a fresh worker
    finishes from the graph alone."""
    wg.add_task(task_id="k1", title="k", spec="do work", capability=["summarize"])
    # worker leases then 'crashes' (process killed -9): lease held, no completion
    leased = wg.lease("k1", owner="dead-worker", model="ollama:qwen2.5:14b", ttl=1.0)
    assert leased["status"] == "leased"
    # simulate time passing beyond the lease TTL
    wg.reclaim_expired(now=time.time() + 10_000)
    assert wg.get("k1")["status"] == "ready"
    # a fresh tick re-leases and completes from the graph alone
    out = driver.run_once(wg, tmp_path / "artifacts", available=["ollama:qwen2.5:14b"])
    assert out["action"] == "completed"
    assert wg.get("k1")["status"] == "done"
    assert wg.get("k1")["attempt"] >= 2  # crashed attempt + resume attempt


def test_serve_processes_then_escalates(wg, tmp_path, stub_ollama):
    wg.add_task(task_id="s1", title="sum", spec="summarize", capability=["summarize"])
    events = []
    summary = driver.serve(
        wg, tmp_path / "artifacts",
        max_ticks=10, poll_interval=0.0,
        idle_escalate_after=2,
        on_event=events.append,
        sleep=lambda s: None,  # no real waiting
    )
    assert summary["completed"] == 1
    # after the one task completes, the loop goes idle and escalates (bounded)
    actions = [e["action"] for e in events]
    assert "completed" in actions
    assert actions[-1] in ("idle", "needs_human")  # ended on an idle escalation


def test_run_once_routes_around_rate_limit(wg, tmp_path, monkeypatch):
    wg.add_task(task_id="s1", title="sum", spec="summarize", capability=["summarize"])

    class Limited(workers.Worker):
        model = "ollama:qwen2.5:14b"
        autonomous = True

        def run(self, task, artifacts_dir):
            return workers.WorkerResult(False, self.model, task["id"], error="429 rate limit exceeded")

    monkeypatch.setattr(driver.workers, "make_worker", lambda m: Limited())
    out = driver.run_once(wg, tmp_path / "art",
                          available=["ollama:qwen2.5:14b", "tool:deterministic"])
    assert out["action"] == "rate_limited"
    assert out["model"] == "ollama:qwen2.5:14b"
    # released back to ready (not failed) — another model / a fresh invocation resumes it
    assert wg.get("s1")["status"] == "ready"


def test_serve_cools_down_rate_limited_model(wg, tmp_path, monkeypatch):
    wg.add_task(task_id="s1", title="sum", spec="x", capability=["summarize"])
    calls = {"n": 0}

    class Limited(workers.Worker):
        model = "ollama:qwen2.5:14b"
        autonomous = True

        def run(self, task, artifacts_dir):
            calls["n"] += 1
            return workers.WorkerResult(False, self.model, task["id"], error="quota exceeded")

    monkeypatch.setattr(driver.workers, "make_worker", lambda m: Limited())
    monkeypatch.setattr(driver.workers, "available_models",
                        lambda: ["ollama:qwen2.5:14b", "tool:deterministic"])
    summary = driver.serve(wg, tmp_path / "art", max_ticks=5, poll_interval=0.0,
                           idle_escalate_after=2, sleep=lambda s: None)
    assert summary["rate_limited"] >= 1
    assert wg.get("s1")["status"] == "ready"
    assert calls["n"] == 1  # tried once, then cooled down (not hammered every tick)


def test_parallel_serve_no_double_processing(tmp_path, monkeypatch):
    """N concurrent worker threads over one graph: the atomic lease guarantees
    each task is processed exactly once (the '3+ models at once' safety proof)."""
    db = tmp_path / "wg.db"
    g = WorkGraph(db)
    M = 6
    for i in range(M):
        g.add_task(task_id=f"t{i}", title=f"t{i}", spec="summarize this", capability=["summarize"])
    g.close()

    monkeypatch.setattr(workers, "_ollama_api", lambda *a, **k: {"response": "deliverable"})
    monkeypatch.setattr(workers, "available_models",
                        lambda **k: ["ollama:qwen2.5:14b", "tool:deterministic"])

    summary = driver.parallel_serve(
        str(db), tmp_path / "art", n_workers=4,
        max_ticks=None, poll_interval=0.0, idle_escalate_after=2,
    )
    assert summary["completed"] == M

    g2 = WorkGraph(db)
    try:
        tasks = g2.all_tasks()
        assert all(t["status"] == "done" for t in tasks)
        assert all(t["attempt"] == 1 for t in tasks)  # exactly-once: no re-lease/double run
    finally:
        g2.close()


def test_serve_watch_stays_resident_until_max_ticks(wg, tmp_path):
    # empty graph → idle every tick. Without watch, idle_escalate_after=2 stops at
    # tick 2; watch mode stays resident (PoC/debug monitoring) until max_ticks.
    events = []
    summary = driver.serve(
        wg, tmp_path / "art", max_ticks=4, poll_interval=0.0,
        idle_escalate_after=2, watch=True, on_event=events.append, sleep=lambda s: None,
    )
    assert summary["ticks"] == 4  # did NOT exit early on idle
    assert any(e.get("action") == "watch" for e in events)  # heartbeat with graph counts


def test_serve_halts_at_auth_gate(wg, tmp_path, monkeypatch):
    wg.add_task(task_id="s1", title="sum", spec="summarize", capability=["summarize"])

    class AuthFail(workers.Worker):
        model = "ollama:qwen2.5:14b"
        autonomous = True

        def run(self, task, artifacts_dir):
            return workers.WorkerResult(
                False, self.model, task["id"], error="Error: please re-login to continue"
            )

    monkeypatch.setattr(driver.workers, "make_worker", lambda m: AuthFail())
    monkeypatch.setattr(driver.workers, "available_models",
                        lambda: ["ollama:qwen2.5:14b", "tool:deterministic"])

    events = []
    summary = driver.serve(
        wg, tmp_path / "artifacts", max_ticks=5, poll_interval=0.0,
        on_event=events.append, sleep=lambda s: None,
    )
    assert summary["last"]["action"] == "auth_halt"
    # task released back to ready (not failed) — a human re-login can resume it
    assert wg.get("s1")["status"] == "ready"

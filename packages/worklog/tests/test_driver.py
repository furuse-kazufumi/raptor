"""Driver tests — one-tick scheduling, human-gating, kill-and-resume, escalation.

Ollama is stubbed at the subprocess boundary so no real model runs; the full
lease -> run -> commit path is exercised."""

import json
import sys
import time
from pathlib import Path

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


class _Author(workers.Worker):
    model = "ollama:qwen2.5:14b"
    autonomous = True

    def run(self, task, artifacts_dir):
        return workers.WorkerResult(True, self.model, task["id"], result_ref="r",
                                    output="the result", duration=0.1)


class _Verifier(workers.Worker):
    model = "codex"
    autonomous = True

    def __init__(self, verdict):
        self.verdict = verdict

    def run(self, task, artifacts_dir):
        return workers.WorkerResult(True, self.model, task["id"], output=self.verdict, duration=0.1)


def test_run_once_verify_pass_records_verifier(wg, tmp_path, monkeypatch):
    wg.add_task(task_id="s1", title="s", spec="summarize", capability=["summarize"])
    monkeypatch.setattr(driver.workers, "make_worker",
                        lambda m: _Author() if m.startswith("ollama") else _Verifier("PASS ok"))
    out = driver.run_once(wg, tmp_path / "art",
                          available=["ollama:qwen2.5:14b", "codex", "tool:deterministic"], verify=True)
    assert out["action"] == "completed"
    assert out["verified_by"] and out["verifier"] == "codex"
    t = wg.get("s1")
    assert t["status"] == "done" and t["verified_by"]


def test_run_once_verify_fail_surfaces_human(wg, tmp_path, monkeypatch):
    wg.add_task(task_id="s1", title="s", spec="summarize", capability=["summarize"])
    monkeypatch.setattr(driver.workers, "make_worker",
                        lambda m: _Author() if m.startswith("ollama") else _Verifier("FAIL: wrong"))
    out = driver.run_once(wg, tmp_path / "art",
                          available=["ollama:qwen2.5:14b", "codex", "tool:deterministic"], verify=True)
    assert out["action"] == "needs_human"
    assert out["reason"] == "verify_failed"
    assert wg.get("s1")["status"] == "ready"  # released, not auto-completed


def test_run_once_completes_tool_task_autonomously(wg, tmp_path):
    """Acceptance path: a `tool` task runs a real command with no LLM in the loop
    and lands its artifact in artifacts/<id>/ (where the -Web gallery scans)."""
    spec = json.dumps({
        "cmd": [sys.executable, "-c", "import sys;open(sys.argv[1],'w').write('rendered')",
                "<OUT>.txt"],
        "produces": "<OUT>.txt",
        "timeout": 120,
    })
    wg.add_task(task_id="t1", title="render", spec=spec, capability=["tool"])
    out = driver.run_once(wg, tmp_path / "art", available=["tool:command", "tool:deterministic"])
    assert out["action"] == "completed"
    assert out["model"] == "tool:command"
    ref = Path(out["result_ref"])
    assert ref.is_file() and ref.parent.resolve() == (tmp_path / "art" / "t1").resolve()
    assert wg.get("t1")["status"] == "done"


def test_lease_ttl_for_tool_task_uses_spec_timeout():
    tool_spec = json.dumps({"cmd": ["x"], "timeout": 1800})
    assert driver._lease_ttl_for({"spec": tool_spec}, "tool:command") == 1800 + driver._TOOL_LEASE_MARGIN
    # spec omits timeout → the worker's own 900s default, plus the margin
    assert (driver._lease_ttl_for({"spec": json.dumps({"cmd": ["x"]})}, "tool:command")
            == 900 + driver._TOOL_LEASE_MARGIN)
    # LLM workers keep the graph default
    assert driver._lease_ttl_for({"spec": "a prompt"}, "ollama:qwen2.5:14b") is None
    # non-JSON tool spec → default TTL (the worker rejects the task anyway)
    assert driver._lease_ttl_for({"spec": "not json"}, "tool:command") is None


def test_long_tool_task_lease_outlives_default_ttl(wg, tmp_path, monkeypatch):
    """A multi-hour sweep must not have its lease reclaimed mid-run: reclaim would
    re-lease it and start a *second* concurrent run of the same heavy command,
    while the first run's complete() fails on the now-stale lease."""
    spec = json.dumps({"cmd": [sys.executable, "-c", "pass"], "timeout": 7200})
    wg.add_task(task_id="t3", title="sweep", spec=spec, capability=["tool"])
    seen = {}
    real_lease = wg.lease

    def _spy(task_id, owner, model, ttl=None):
        seen["ttl"] = ttl
        return real_lease(task_id, owner=owner, model=model, ttl=ttl)

    monkeypatch.setattr(wg, "lease", _spy)
    out = driver.run_once(wg, tmp_path / "art", available=["tool:command"])
    assert out["action"] == "completed"
    assert seen["ttl"] == 7200 + driver._TOOL_LEASE_MARGIN
    assert seen["ttl"] > wg.lease_ttl  # the whole point: longer than the default


def test_verify_skips_deterministic_tool_worker(wg, tmp_path, monkeypatch):
    """A render has nothing a different provider can verify — and a bogus FAIL
    would halt autonomous progress. `verify=True` must not route tool results to
    an LLM verifier."""
    spec = json.dumps({"cmd": [sys.executable, "-c", "pass"]})
    wg.add_task(task_id="t2", title="render", spec=spec, capability=["tool"])

    def _boom(*a, **k):  # a verifier must never be picked for a tool result
        raise AssertionError("verifier must not run for a deterministic tool task")

    monkeypatch.setattr(driver, "_pick_verifier", _boom)
    out = driver.run_once(wg, tmp_path / "art",
                          available=["tool:command", "codex"], verify=True)
    assert out["action"] == "completed"
    assert out["verified_by"] is None  # self-verifying, not provider-verified
    assert wg.get("t2")["status"] == "done"


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

"""Bounded-memory compaction tests (NN stubbed — the hard cap is deterministic)."""

from packages.worklog import compact, workers
from packages.worklog.store import WorkGraph


def test_summarize_under_budget_is_unchanged():
    assert compact.summarize_bounded("short text", 100) == "short text"


def test_summarize_hard_caps_overlong_nn_output(monkeypatch):
    # NN ignores the budget and returns 500 chars → code enforces <= max_chars
    monkeypatch.setattr(workers, "ollama_generate", lambda *a, **k: "X" * 500)
    out = compact.summarize_bounded("y" * 1000, 100)
    assert len(out) <= 100
    assert out.endswith("…")


def test_summarize_falls_back_to_truncation_when_nn_down(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no ollama")

    monkeypatch.setattr(workers, "ollama_generate", boom)
    out = compact.summarize_bounded("z" * 1000, 50)
    assert len(out) <= 50  # bound holds even without the NN


def test_compact_handoff_is_bounded(monkeypatch, tmp_path):
    monkeypatch.setattr(workers, "ollama_generate", lambda *a, **k: "S" * 5000)
    wg = WorkGraph(tmp_path / "wg.db")
    try:
        wg.add_task(task_id="a", title="a", spec="x" * 2000, project="p", capability=["reason"])
        wg.add_task(task_id="b", title="b", spec="y" * 2000, project="p", capability=["reason"])
        out = compact.compact_handoff(wg, "p", max_chars=300)
        assert 0 < len(out) <= 300
    finally:
        wg.close()

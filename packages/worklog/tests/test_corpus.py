"""Per-project progress corpus (navigable INDEX.md, loaded on resume)."""

from packages.worklog import corpus, workers
from packages.worklog.store import WorkGraph


def test_build_project_corpus_writes_navigable_index(monkeypatch, tmp_path):
    monkeypatch.setattr(workers, "ollama_generate", lambda *a, **k: "bounded handoff summary")
    wg = WorkGraph(tmp_path / "wg.db")
    try:
        wg.add_task(task_id="o1", title="open task", spec="x" * 2000,
                    project="p", capability=["reason"], priority=1)
        wg.add_task(task_id="d1", title="done task", spec="y" * 2000,
                    project="p", capability=["summarize"])
        wg.lease("d1", owner="w", model="ollama:x")
        wg.complete("d1", owner="w", result_ref="out/d1.md", result_by="ollama:x")

        d = corpus.build_project_corpus(wg, "p", tmp_path / "corpus")
        idx = d / "INDEX.md"
        assert idx.exists()
        text = idx.read_text(encoding="utf-8")
        assert "open task" in text          # open work listed
        assert "done task" in text          # finished fact listed
        assert "out/d1.md" in text          # artifact link for navigation
        assert "bounded handoff summary" in text  # bounded handoff at the top
    finally:
        wg.close()

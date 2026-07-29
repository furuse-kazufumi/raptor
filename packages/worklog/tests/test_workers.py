"""Worker adapter tests (offline — real ollama/codex calls are e2e, not unit)."""

from pathlib import Path

from packages.worklog import workers
from packages.worklog.workers import (
    ClaudeWorker,
    CodexWorker,
    CopilotWorker,
    OllamaWorker,
    make_worker,
    safe_env,
)


def test_make_worker_types():
    assert isinstance(make_worker("ollama:qwen2.5:14b"), OllamaWorker)
    assert isinstance(make_worker("codex"), CodexWorker)
    assert isinstance(make_worker("claude"), ClaudeWorker)
    assert isinstance(make_worker("copilot"), CopilotWorker)


def test_claude_worker_is_human_gated():
    res = ClaudeWorker().run({"id": "t1", "spec": "reason hard", "project": "p", "title": "t"}, Path("."))
    assert res.ok is False
    assert res.needs_human is True


def test_safe_env_strips_shell_eval_vars(monkeypatch):
    monkeypatch.setenv("EDITOR", "vim; rm -rf /")
    monkeypatch.setenv("PAGER", "less")
    env = safe_env()
    assert "EDITOR" not in env and "PAGER" not in env


def test_ollama_worker_writes_artifact(monkeypatch, tmp_path):
    # stub the ollama HTTP API so no real model is invoked
    monkeypatch.setattr(workers, "_ollama_api", lambda *a, **k: {"response": "the deliverable text"})

    w = OllamaWorker("ollama:llama3.1")
    task = {"id": "t42", "spec": "summarize X", "project": "p", "title": "t"}
    res = w.run(task, tmp_path)
    assert res.ok is True
    assert res.result_ref and Path(res.result_ref).exists()
    body = Path(res.result_ref).read_text(encoding="utf-8")
    assert "the deliverable text" in body
    assert "produced_by: ollama:llama3.1" in body


def test_ollama_worker_reports_api_error(monkeypatch, tmp_path):
    def _boom(*a, **k):
        raise workers.urllib.error.URLError("unreachable")

    monkeypatch.setattr(workers, "_ollama_api", _boom)
    res = OllamaWorker("ollama:llama3.1").run({"id": "t", "spec": "s", "project": "p", "title": "t"}, tmp_path)
    assert res.ok is False and "unreachable" in (res.error or "")


def test_clean_output_strips_ansi_and_spinner():
    raw = "answer text\x1b[2D\x1b[K done\r final line"
    cleaned = workers.clean_output(raw)
    assert "\x1b" not in cleaned
    assert "[2D" not in cleaned and "[K" not in cleaned
    assert "final line" in cleaned


def test_available_models_always_has_tool(monkeypatch):
    def _boom(*a, **k):
        raise workers.urllib.error.URLError("no server")

    monkeypatch.setattr(workers, "_ollama_api", _boom)          # ollama server down
    monkeypatch.setattr(workers.shutil, "which", lambda name: None)  # no CLIs installed
    models = workers.available_models()
    assert "tool:deterministic" in models

"""Worker adapter tests (offline — real ollama/codex calls are e2e, not unit)."""

import json
import sys
from pathlib import Path

from packages.worklog import workers
from packages.worklog.workers import (
    ClaudeWorker,
    CodexWorker,
    CommandWorker,
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
    assert isinstance(make_worker("tool:command"), CommandWorker)


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
    # the command worker needs no external CLI — always routable
    assert "tool:command" in models
    # INVARIANT: only models make_worker() can actually build may be advertised.
    # 'tool:deterministic' (routing.LOCAL_FIRST['scan']) has no adapter yet, so it
    # must NOT be advertised — advertising it would hand the driver an unbuildable
    # model (make_worker raises), the bug this guards against.
    assert "tool:deterministic" not in models
    for m in models:
        workers.make_worker(m)  # must not raise for any advertised model


# ── CommandWorker (deterministic tool/command execution) ───────────────


def _cmd_task(spec: dict, task_id: str = "c1") -> dict:
    return {"id": task_id, "spec": json.dumps(spec), "project": "p", "title": "render"}


def test_command_worker_runs_subprocess_and_captures_artifact(tmp_path):
    task = _cmd_task(
        {
            "cmd": [sys.executable, "-c",
                    "import sys;open(sys.argv[1],'w').write('ok')", "<OUT>.txt"],
            "produces": "<OUT>.txt",
            "timeout": 120,
        }
    )
    res = CommandWorker().run(task, tmp_path)
    assert res.ok is True, res.error
    assert res.result_ref
    ref = Path(res.result_ref)
    assert ref.is_file()
    assert ref.read_text(encoding="utf-8") == "ok"
    # artifact must land inside artifacts_dir/<task_id>/ (the gallery scans there)
    assert ref.parent.resolve() == (tmp_path / "c1").resolve()


def test_command_worker_copies_external_artifact_into_task_dir(tmp_path):
    external = tmp_path / "elsewhere" / "render.gif"
    external.parent.mkdir(parents=True)
    task = _cmd_task(
        {
            "cmd": [sys.executable, "-c",
                    "import sys;open(sys.argv[1],'wb').write(b'GIF89a')", str(external)],
            "produces": str(external),
        },
        task_id="c2",
    )
    res = CommandWorker().run(task, tmp_path)
    assert res.ok is True, res.error
    ref = Path(res.result_ref)
    assert ref.parent.resolve() == (tmp_path / "c2").resolve()
    assert ref.name == "render.gif"
    assert ref.read_bytes() == b"GIF89a"


def test_command_worker_falls_back_to_newest_file_in_task_dir(tmp_path):
    # no `produces` — the command writes straight into <OUT>'s directory
    task = _cmd_task(
        {
            "cmd": [sys.executable, "-c",
                    "import os,sys;d=os.path.dirname(sys.argv[1]);"
                    "open(os.path.join(d,'frame.png'),'wb').write(b'\\x89PNG')", "<OUT>"],
        },
        task_id="c3",
    )
    res = CommandWorker().run(task, tmp_path)
    assert res.ok is True, res.error
    assert Path(res.result_ref).name == "frame.png"


def test_command_worker_rejects_bad_json_spec(tmp_path):
    res = CommandWorker().run({"id": "c4", "spec": "not json at all", "project": "p", "title": "t"}, tmp_path)
    assert res.ok is False
    assert "JSON" in (res.error or "")


def test_command_worker_rejects_non_list_cmd(tmp_path):
    # fail-closed: no shell strings, ever (raptor rule)
    res = CommandWorker().run(_cmd_task({"cmd": "echo hi && rm -rf /"}, "c5"), tmp_path)
    assert res.ok is False
    assert "cmd" in (res.error or "")


def test_command_worker_reports_failure_exit_code(tmp_path):
    task = _cmd_task(
        {"cmd": [sys.executable, "-c", "import sys;sys.stderr.write('boom');sys.exit(3)"]},
        task_id="c6",
    )
    res = CommandWorker().run(task, tmp_path)
    assert res.ok is False
    assert "exit 3" in (res.error or "")


def test_command_worker_fails_when_declared_artifact_missing(tmp_path):
    # rc==0 but the promised file was never written → broken contract, fail-closed
    task = _cmd_task({"cmd": [sys.executable, "-c", "pass"], "produces": "<OUT>.gif"}, "c7")
    res = CommandWorker().run(task, tmp_path)
    assert res.ok is False
    assert "produces" in (res.error or "")


def test_command_worker_times_out(tmp_path):
    task = _cmd_task(
        {"cmd": [sys.executable, "-c", "import time;time.sleep(30)"], "timeout": 1},
        task_id="c8",
    )
    res = CommandWorker().run(task, tmp_path)
    assert res.ok is False
    assert "timeout" in (res.error or "")


def test_command_worker_uses_safe_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR", "vim; rm -rf /")
    task = _cmd_task(
        {
            "cmd": [sys.executable, "-c",
                    "import os,sys;open(sys.argv[1],'w').write(os.environ.get('EDITOR','')"
                    "+'|'+os.environ.get('WORKLOG_MARK',''))", "<OUT>.txt"],
            "produces": "<OUT>.txt",
            "env": {"WORKLOG_MARK": "from-spec"},
        },
        task_id="c9",
    )
    res = CommandWorker().run(task, tmp_path)
    assert res.ok is True, res.error
    assert Path(res.result_ref).read_text(encoding="utf-8") == "|from-spec"


def test_command_worker_writes_command_log(tmp_path):
    task = _cmd_task(
        {"cmd": [sys.executable, "-c", "print('hello from the render')"]},
        task_id="c10",
    )
    res = CommandWorker().run(task, tmp_path)
    assert res.ok is True, res.error
    log = tmp_path / "c10" / "command.log"
    assert log.is_file()
    assert "hello from the render" in log.read_text(encoding="utf-8")

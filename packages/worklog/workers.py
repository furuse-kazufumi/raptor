"""Worker adapters — the stateless, crash-only executors.

A worker leases one task, does bounded work from the task's self-contained
`spec`, writes a content artifact + provenance, and returns. Local Ollama
workers consume no session/token budget (the "don't consume the session" path);
Codex runs headless read-only; Claude is honestly **human-gated** (it launches
via node-pty + a human Enter, never auto-respawned — the ccr limit). Copilot is
a read-only verify worker.

Security (raptor rule): subprocesses use list-arg invocation + a sanitized env
(no shell-evaluated vars); task specs are never interpolated into a shell string.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ANSI CSI / OSC control sequences (ollama's progress spinner leaks these into
# piped stdout on some builds); strip so artifacts are clean text.
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")


def clean_output(text: str) -> str:
    """Strip ANSI escapes and spinner carriage-return overwrites from tool output."""
    text = _ANSI_RE.sub("", text)
    # collapse carriage-return overwrites: keep the final segment of each line
    lines = []
    for line in text.split("\n"):
        if "\r" in line:
            line = line.split("\r")[-1]
        lines.append(line)
    return "\n".join(lines).strip()

# env vars that can be shell-evaluated by child tools — strip before spawning
_UNSAFE_ENV = ("TERMINAL", "EDITOR", "VISUAL", "BROWSER", "PAGER")

DEFAULT_OLLAMA_TIMEOUT = float(os.environ.get("WORKLOG_OLLAMA_TIMEOUT", "300"))
DEFAULT_CODEX_TIMEOUT = float(os.environ.get("WORKLOG_CODEX_TIMEOUT", "300"))
# keep_alive="0" → unload the model right after each call so the orchestration does
# not reside in VRAM during heavy AI-dev execution/eval (model reload is cheap; the
# work-graph does its handoff at PDCA-cycle boundaries, not by staying resident).
# Raise WORKLOG_OLLAMA_KEEP_ALIVE (e.g. "5m") to trade residency for throughput.
DEFAULT_OLLAMA_KEEP_ALIVE = os.environ.get("WORKLOG_OLLAMA_KEEP_ALIVE", "0")


def safe_env() -> dict:
    env = dict(os.environ)
    for k in _UNSAFE_ENV:
        env.pop(k, None)
    return env


def _ollama_host() -> str:
    """Resolve the Ollama base URL from the environment. NEVER logged/disclosed
    (raptor rule: never reveal the Ollama server location)."""
    h = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434").strip()
    if not h.startswith(("http://", "https://")):
        h = "http://" + h
    return h.rstrip("/")


def _ollama_api(path: str, payload: dict | None = None, timeout: float = 30.0) -> Any:
    """Call the Ollama HTTP API (clean output, no TTY control chars). Returns the
    decoded JSON. Errors never include the host (non-disclosure)."""
    url = _ollama_host() + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method="POST" if data else "GET",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


@dataclass
class WorkerResult:
    ok: bool
    model: str
    task_id: str
    result_ref: str | None = None
    output: str = ""
    error: str | None = None
    needs_human: bool = False
    duration: float = 0.0
    meta: dict = field(default_factory=dict)


def _artifact_path(artifacts_dir: Path, task_id: str) -> Path:
    d = artifacts_dir / task_id
    d.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    return d / f"result-{stamp}.md"


def _write_artifact(path: Path, task: dict, model: str, output: str) -> None:
    header = (
        f"# worklog result\n\n"
        f"- task_id: {task['id']}\n"
        f"- project: {task.get('project','')}\n"
        f"- title: {task.get('title','')}\n"
        f"- produced_by: {model}\n"
        f"- produced_at: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"
        f"---\n\n"
    )
    path.write_text(header + output, encoding="utf-8")


def ollama_generate(model: str, prompt: str, timeout: float = DEFAULT_OLLAMA_TIMEOUT) -> str:
    """One-shot local generation via the Ollama HTTP API. Returns clean text.
    Reusable outside the worker protocol (e.g. bounded-summary compaction)."""
    name = model.split(":", 1)[1] if model.startswith("ollama:") else model
    data = _ollama_api(
        "/api/generate",
        {"model": name, "prompt": prompt, "stream": False, "keep_alive": DEFAULT_OLLAMA_KEEP_ALIVE},
        timeout=timeout,
    )
    return clean_output(str(data.get("response", "")))


class Worker:
    """Base worker. Subclasses implement `run`."""

    model = "abstract"
    autonomous = False  # may the driver run this unattended?

    def run(self, task: dict, artifacts_dir: Path) -> WorkerResult:  # pragma: no cover
        raise NotImplementedError


class OllamaWorker(Worker):
    """Local Ollama model — no session/token consumption. The autonomous, free
    worker for cheap-tier tasks (triage/summarize/codegen-draft)."""

    autonomous = True

    def __init__(self, model: str, timeout: float = DEFAULT_OLLAMA_TIMEOUT):
        # model like "ollama:qwen2.5:14b" -> ollama name "qwen2.5:14b"
        self.model = model
        self.ollama_name = model.split(":", 1)[1] if model.startswith("ollama:") else model
        self.timeout = timeout

    def run(self, task: dict, artifacts_dir: Path) -> WorkerResult:
        prompt = (
            "You are an autonomous worker executing one self-contained task.\n"
            "Produce the concrete deliverable the task asks for. Be direct.\n\n"
            "=== TASK SPEC ===\n" + task["spec"] + "\n=== END SPEC ===\n"
        )
        start = time.time()
        try:
            data = _ollama_api(
                "/api/generate",
                {"model": self.ollama_name, "prompt": prompt, "stream": False,
                 "keep_alive": DEFAULT_OLLAMA_KEEP_ALIVE},
                timeout=self.timeout,
            )
        except urllib.error.URLError:
            # do not include the host in the error (non-disclosure)
            return WorkerResult(False, self.model, task["id"],
                                error="ollama api unreachable", duration=time.time() - start)
        except Exception as exc:  # noqa: BLE001
            return WorkerResult(False, self.model, task["id"],
                                error=f"ollama api error: {type(exc).__name__}", duration=time.time() - start)
        dur = time.time() - start
        out = clean_output(str(data.get("response", "")))
        if not out:
            return WorkerResult(False, self.model, task["id"],
                                error="ollama returned empty response", duration=dur)
        path = _artifact_path(artifacts_dir, task["id"])
        _write_artifact(path, task, self.model, out)
        return WorkerResult(True, self.model, task["id"], result_ref=str(path), output=out, duration=dur)


class CodexWorker(Worker):
    """Codex CLI, headless, read-only. Fixed-quota escalation / review worker."""

    model = "codex"
    autonomous = True

    def __init__(self, timeout: float = DEFAULT_CODEX_TIMEOUT):
        self.timeout = timeout

    def run(self, task: dict, artifacts_dir: Path) -> WorkerResult:
        exe = shutil.which("codex")
        if not exe:
            return WorkerResult(False, self.model, task["id"], error="codex not found")
        start = time.time()
        try:
            proc = subprocess.run(
                [exe, "exec", "-s", "read-only", task["spec"]],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=self.timeout, env=safe_env(),
            )
        except subprocess.TimeoutExpired:
            return WorkerResult(False, self.model, task["id"], error=f"codex timeout after {self.timeout}s",
                                duration=time.time() - start)
        except Exception as exc:  # noqa: BLE001
            return WorkerResult(False, self.model, task["id"], error=str(exc), duration=time.time() - start)
        dur = time.time() - start
        out = clean_output(proc.stdout or "")
        if proc.returncode != 0 and not out:
            return WorkerResult(False, self.model, task["id"],
                                error=f"codex exit {proc.returncode}: {(proc.stderr or '').strip()[:400]}",
                                duration=dur)
        path = _artifact_path(artifacts_dir, task["id"])
        _write_artifact(path, task, self.model, out)
        return WorkerResult(True, self.model, task["id"], result_ref=str(path), output=out, duration=dur)


class ClaudeWorker(Worker):
    """Claude Code — deep reasoning tier. Honestly HUMAN-GATED: it cannot be
    auto-restarted/re-logged-in (project_ccr_automation_limits). The autonomous
    driver never runs it unattended; it surfaces the task for a human to launch
    via `rp <project>` (node-pty + human Enter)."""

    model = "claude"
    autonomous = False

    def run(self, task: dict, artifacts_dir: Path) -> WorkerResult:
        return WorkerResult(
            False, self.model, task["id"], needs_human=True,
            error="claude is human-gated; launch via `rp <project>` and Enter (no auto-restart)",
            meta={"reason": "human_gated"},
        )


class CopilotWorker(Worker):
    """GitHub Copilot CLI — read-only verify worker (different-provider check)."""

    model = "copilot"
    autonomous = True

    def __init__(self, timeout: float = DEFAULT_CODEX_TIMEOUT):
        self.timeout = timeout

    def run(self, task: dict, artifacts_dir: Path) -> WorkerResult:
        exe = shutil.which("copilot")
        if not exe:
            return WorkerResult(False, self.model, task["id"], error="copilot not found")
        start = time.time()
        try:
            proc = subprocess.run(
                [exe, "-p", task["spec"]],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=self.timeout, env=safe_env(),
            )
        except subprocess.TimeoutExpired:
            return WorkerResult(False, self.model, task["id"], error=f"copilot timeout after {self.timeout}s",
                                duration=time.time() - start)
        except Exception as exc:  # noqa: BLE001
            return WorkerResult(False, self.model, task["id"], error=str(exc), duration=time.time() - start)
        dur = time.time() - start
        out = clean_output(proc.stdout or "")
        path = _artifact_path(artifacts_dir, task["id"])
        _write_artifact(path, task, self.model, out)
        return WorkerResult(proc.returncode == 0 or bool(out), self.model, task["id"],
                            result_ref=str(path), output=out, duration=dur)


def make_worker(model: str) -> Worker:
    """Factory: model id -> worker adapter."""
    if model.startswith("ollama"):
        return OllamaWorker(model)
    if model == "codex":
        return CodexWorker()
    if model == "claude":
        return ClaudeWorker()
    if model == "copilot":
        return CopilotWorker()
    raise ValueError(f"no worker adapter for model: {model!r}")


def available_models(ollama_timeout: float = 20.0) -> list[str]:
    """Probe which worker models are usable right now (for routing).

    Returns model ids like 'ollama:qwen2.5:14b', 'codex', 'claude', 'copilot',
    plus 'tool:deterministic'. Never raises; unreachable Ollama yields no local
    models. Does not log the Ollama host (raptor rule)."""
    models: list[str] = ["tool:deterministic"]
    try:
        tags = _ollama_api("/api/tags", timeout=ollama_timeout)
        for m in tags.get("models", []):
            name = str(m.get("name", "")).strip()
            if name:
                models.append(f"ollama:{name}")
    except Exception:  # noqa: BLE001
        pass  # server unreachable → no local models (never raises, never logs host)
    for cli in ("codex", "claude", "copilot"):
        if shutil.which(cli):
            models.append(cli)
    return models

"""Capability -> worker routing (local-first, deterministic).

The scheduler is deterministic and keeps no LLM in the hot loop; routing is a
plain lookup table, not a model call. Local-first: prefer on-box Ollama models
(no session/token consumption) and escalate to metered providers (Codex, Claude)
only for capabilities a local model cannot do well. `on_prem_only` tasks are
structurally confined to local models.

A learned router (trained on the graph's `attempt` log) is a later optimization
(spec §5, Phase 3); this table is the honest starting point.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

# Local-first escalation lists per capability. Left = cheapest/local; right =
# most capable/most expensive. "tool:*" means a deterministic tool, no LLM.
# Note on qwen2.5:72b: strongest local model but VRAM-limited on this box
# (58 GB → partial CPU offload, ~38 s/short-gen), so it sits AFTER the faster
# local models — reachable as a heavy local fallback, never the hot-path default.
LOCAL_FIRST: dict[str, list[str]] = {
    "scan":      ["tool:deterministic"],
    "triage":    ["ollama:llama3.1", "ollama:qwen2.5:14b"],
    "summarize": ["ollama:qwen2.5:14b", "ollama:qwen2.5-coder:32b", "ollama:qwen2.5:72b", "codex"],
    "codegen":   ["ollama:qwen2.5-coder:32b", "ollama:qwen2.5:72b", "codex", "claude"],
    "web":       ["claude"],
    "reason":    ["claude"],  # flagship cold-start tasks stay human-gated (honest, F1)
    "review":    ["codex", "copilot", "claude"],  # verify: a different provider than the author
    "tool":      ["tool:command"],  # run a command; spec is JSON, no LLM involved
}

# Precedence when a task carries several capability tags: route to the model that
# can handle the *hardest* one (higher index = harder / more capable required).
# `tool` sits last (most dominant) not because it is "hardest" but because it is
# *exclusive*: a tool task's spec is a command in JSON, which no LLM can serve —
# so a mixed tag set must still reach CommandWorker (fail-closed against a
# mis-tagged render being handed to a model as a prompt).
HARDNESS = ["scan", "triage", "summarize", "review", "web", "codegen", "reason", "tool"]

# Default when a task has no capability tag: unknown complexity → the strongest,
# human-gated tier (honest: most real cold-start tasks are the hard ones).
DEFAULT_CAPABILITY = "reason"


def _is_local(model: str) -> bool:
    return model.startswith(("ollama", "tool:"))


def _resolve_available(candidate: str, avail: set[str]) -> str | None:
    """Match a routing candidate against actually-available model ids, tolerant
    of Ollama tag suffixes (candidate 'ollama:llama3.1' matches available
    'ollama:llama3.1:latest'). Returns the concrete available id, or None."""
    if candidate in avail:
        return candidate
    # Deterministic: iterate a SORTED view (a set's order is arbitrary) and prefer
    # the canonical ':latest' tag over any other suffix, so the same available set
    # always resolves the same concrete id.
    matches = sorted(a for a in avail if a == candidate + ":latest" or a.startswith(candidate + ":"))
    for a in matches:
        if a == candidate + ":latest":
            return a
    return matches[0] if matches else None


def dominant_capability(capabilities: Sequence[str]) -> str:
    """Return the hardest capability among the task's tags (routing driver)."""
    caps = [c for c in capabilities if c in LOCAL_FIRST]
    if not caps:
        return DEFAULT_CAPABILITY
    return max(caps, key=lambda c: HARDNESS.index(c) if c in HARDNESS else -1)


def candidates(capabilities: Sequence[str], on_prem_only: bool = False) -> list[str]:
    """Ordered local-first candidate models for a task's capabilities."""
    cap = dominant_capability(capabilities)
    models = list(LOCAL_FIRST.get(cap, LOCAL_FIRST[DEFAULT_CAPABILITY]))
    if on_prem_only:
        models = [m for m in models if _is_local(m)]
    return models


def route(
    capabilities: Sequence[str],
    on_prem_only: bool,
    available: Iterable[str],
    prefer_local: bool = True,
) -> str | None:
    """Pick the model to run a task, given which worker models are available.

    `available` is the set/list of usable worker model ids (e.g. what
    `ollama list` + installed CLIs report). Returns the first candidate that is
    available, honoring local-first and the on_prem_only boundary. Returns None
    if nothing available can serve the task.
    """
    avail = set(available)
    cands = candidates(capabilities, on_prem_only)
    if prefer_local:
        local = [m for m in cands if _is_local(m)]
        cloud = [m for m in cands if not _is_local(m)]
        cands = local + cloud
    for m in cands:
        resolved = _resolve_available(m, avail)
        if resolved is not None:
            return resolved
    return None


def autonomous_only(capabilities: Sequence[str], on_prem_only: bool) -> bool:
    """True iff this task can be served entirely by an autonomous (non-Claude,
    non-human-gated) worker — i.e. its dominant capability's local-first choice
    is Ollama or a deterministic tool. Used by the driver to decide what it may
    run unattended vs. what must wait for a human-gated Claude session."""
    cands = candidates(capabilities, on_prem_only)
    return bool(cands) and (cands[0].startswith("ollama") or cands[0].startswith("tool:"))

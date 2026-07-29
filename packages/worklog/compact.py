"""Bounded-memory compaction — keep handoff summaries to a fixed volume.

Two jobs, both keeping the work-graph's memory *bounded* so it never grows without
limit (the crux of sustainable, session-limit-proof development):

1. `summarize_bounded` — compress arbitrary text to at most `max_chars` using a
   local NN (Ollama), with a **deterministic hard cap**: the NN drafts, but code
   enforces the budget (never trust the model to obey a length limit). Falls back
   to head-truncation if the NN is unavailable — the bound holds regardless.

2. `compact_handoff` — regenerate a bounded per-project handoff summary from the
   graph (the replacement for the ever-growing `next_plan` `その9→その8…` stack).

Pruning of finished tasks (drop detail, keep the fact for a period) lives in
`store.WorkGraph.prune_done`; pass `summarize_bounded` as its summarizer to keep a
one-line gist per tombstone.

The summarizer is intentionally thin (a local Ollama call + a deterministic cap)
and fully **pluggable**: `prune_done(summarizer=...)` and any caller can substitute
any existing-OSS summarizer (a HuggingFace pipeline, a LangChain summarize chain,
etc.) — a callable `str -> str` is the whole contract. Nothing here is bespoke.
"""

from __future__ import annotations

from . import workers
from .store import WorkGraph

DEFAULT_HANDOFF_CHARS = 1200
DEFAULT_TOMBSTONE_CHARS = 200
DEFAULT_MODEL = "ollama:qwen2.5:14b"


def summarize_bounded(
    text: str,
    max_chars: int,
    model: str = DEFAULT_MODEL,
    timeout: float = 120.0,
) -> str:
    """Return a summary of `text` that is guaranteed to be <= max_chars.
    Under budget already → returned unchanged (no NN call)."""
    text = (text or "").strip()
    if not text or len(text) <= max_chars:
        return text
    prompt = (
        f"Compress the following into at most {max_chars} characters. Keep only the "
        f"most decision-relevant facts: current state, the next concrete action, and any "
        f"blockers. Drop history and fine detail. Output ONLY the summary, no preamble.\n\n"
        + text
    )
    out = ""
    try:
        out = workers.ollama_generate(model, prompt, timeout=timeout).strip()
    except Exception:  # noqa: BLE001
        out = ""
    if not out:
        out = text  # NN unavailable → fall through to deterministic truncation
    if len(out) > max_chars:
        out = out[: max_chars - 1].rstrip() + "…"
    return out


def compact_handoff(
    wg: WorkGraph,
    project: str,
    max_chars: int = DEFAULT_HANDOFF_CHARS,
    model: str = DEFAULT_MODEL,
) -> str:
    """Regenerate a bounded handoff summary for one project from the graph:
    open tasks contribute their spec, finished tasks contribute a one-line fact.
    The result is a fixed-volume replacement for the manual `next_plan` stack."""
    tasks = [t for t in wg.all_tasks() if t["project"] == project]
    if not tasks:
        return ""
    order = {"leased": 0, "ready": 1, "pending": 2, "blocked": 3, "failed": 4, "done": 5}
    tasks.sort(key=lambda t: (order.get(t["status"], 9), t["priority"]))
    parts: list[str] = []
    for t in tasks:
        if t["status"] in ("done", "failed"):
            # finished tasks contribute only the fact (bounded-memory retention)
            parts.append(f"[{t['status']}] {t['title']}")
        else:
            # open tasks contribute their spec (capped per-task so many tasks don't
            # overflow the NN context; the summarizer then compresses to max_chars)
            parts.append(f"[{t['status']}] {t['title']}: {t['spec'][:6000]}")
    blob = "\n".join(parts)
    return summarize_bounded(blob, max_chars, model)

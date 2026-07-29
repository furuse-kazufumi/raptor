"""Per-project progress corpus — load on resume, not held in one context.

Each project's progress (its open task specs, finished-task facts, result
artifacts, and a bounded handoff) is materialized as a small **navigable corpus
directory** — RAD-corpus-shaped — so that resuming a project means *loading its
slice on demand* rather than carrying a monolithic 10 KB blob in every session.
This is the retrieval-side answer to the cold-start context problem (spec §2.4):
the graph holds the durable facts; this projection makes them navigable.

Default output is a stdlib-only `INDEX.md` (handoff + open tasks + finished
facts + artifact links). For a clustered TF-IDF/k-means hierarchy, pass the
project's artifacts through the existing `libexec/raptor-corpus2skill` (opt-in;
that path needs numpy/sklearn) — this module does not reinvent it.
"""

from __future__ import annotations

from pathlib import Path

from . import compact
from .store import WorkGraph

_OPEN = ("ready", "pending", "leased", "blocked")
_DONE = ("done", "failed")


def build_project_corpus(
    wg: WorkGraph,
    project: str,
    out_dir: str | Path,
    model: str = compact.DEFAULT_MODEL,
    max_handoff_chars: int = compact.DEFAULT_HANDOFF_CHARS,
) -> Path:
    """Write `<out_dir>/<project>/INDEX.md` — the on-resume entry point for the
    project. Returns the project corpus directory."""
    tasks = [t for t in wg.all_tasks() if t["project"] == project]
    proj_dir = Path(out_dir) / project
    proj_dir.mkdir(parents=True, exist_ok=True)

    handoff = compact.compact_handoff(wg, project, max_chars=max_handoff_chars, model=model)
    open_tasks = sorted((t for t in tasks if t["status"] in _OPEN), key=lambda x: x["priority"])
    done_tasks = [t for t in tasks if t["status"] in _DONE]

    lines: list[str] = [
        f"# {project} — progress corpus",
        "",
        "_Load this on resume; navigate to the artifact you need. The work-graph is",
        "the source of truth — this is a regenerable projection._",
        "",
        "## Handoff (bounded)",
        "",
        handoff or "(no open work)",
        "",
        f"## Open tasks ({len(open_tasks)})",
        "",
    ]
    for t in open_tasks:
        excerpt = " ".join(t["spec"][:300].split())
        lines.append(
            f"- **{t['title']}** — {t['status']}, p{t['priority']}, {t['capability']}\n  {excerpt}"
        )
    lines += ["", f"## Finished — facts ({len(done_tasks)})", ""]
    for t in done_tasks:
        ref = f" → `{t['result_ref']}`" if t.get("result_ref") else ""
        lines.append(f"- [{t['status']}] {t['title']} ({t['updated_at']}){ref}")

    (proj_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return proj_dir


def build_all(
    wg: WorkGraph,
    out_dir: str | Path,
    model: str = compact.DEFAULT_MODEL,
    max_handoff_chars: int = compact.DEFAULT_HANDOFF_CHARS,
) -> list[Path]:
    projects = sorted({t["project"] for t in wg.all_tasks() if t["project"]})
    return [build_project_corpus(wg, p, out_dir, model, max_handoff_chars) for p in projects]

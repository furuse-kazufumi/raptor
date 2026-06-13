"""Write Corpus2Skill hierarchy to .claude/skills/corpus/<name>/."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.corpus2skill.clusterer import ClusterNode
    from packages.corpus2skill.config import Corpus2SkillConfig


def write_hierarchy(
    root: ClusterNode,
    summaries: dict[str, str],
    config: Corpus2SkillConfig,
    stats: dict,
) -> Path:
    """Write the full skill hierarchy and return the output base directory."""
    base = config.skills_output_dir

    if base.exists() and config.overwrite and not config.resume_summaries:
        shutil.rmtree(base)
    base.mkdir(parents=True, exist_ok=True)

    _write_index(root, base, config)
    _write_node(root, summaries, base, base)
    _write_metadata(root, config, stats, base)

    return base


def _write_index(root: ClusterNode, base: Path, config: Corpus2SkillConfig) -> None:
    lines = [
        "---",
        f"name: corpus/{config.output_name}",
        f"description: Navigable skill hierarchy built from corpus '{config.output_name}'",
        "user-invocable: false",
        "---",
        "",
        f"# {config.output_name} — Skill Index",
        "",
        f"Built from **{root.total_docs}** documents across **{_count_clusters(root)}** clusters.",
        "",
        "## How to Navigate",
        "",
        "1. Read this INDEX.md to find the most relevant top-level cluster.",
        "2. Open that cluster's `SKILL.md` for an overview and sub-cluster links.",
        "3. Descend into sub-clusters as needed until you find target documents.",
        "4. Load individual documents from the `docs/` directory.",
        "",
        "## Top-Level Clusters",
        "",
    ]

    for child in root.children:
        child_local = child.dir_name or child.cluster_id
        rel = f"{child_local}/SKILL.md"
        lines.append(f"- [`{child_local}/`]({rel}) — **{child.label}** ({child.total_docs} docs)")

    if root.is_leaf:
        lines.append("*(Single cluster — all documents in docs/ below)*")

    lines += ["", "## Document Types", ""]
    type_counts: dict[str, int] = {}
    _collect_types(root, type_counts, set())
    for dtype, count in sorted(type_counts.items()):
        lines.append(f"- `{dtype}`: {count} document(s)")

    (base / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def _write_node(
    node: ClusterNode,
    summaries: dict[str, str],
    base: Path,
    node_dir: Path,
) -> None:
    if node.cluster_id == "root":
        # Root node: write docs at base level if leaf, else recurse
        if node.is_leaf:
            _write_docs(node, node_dir)
        else:
            for child in node.children:
                child_local = child.dir_name or child.cluster_id
                child_dir = node_dir / child_local
                child_dir.mkdir(parents=True, exist_ok=True)
                _write_skill_md(child, summaries, child_dir)
                _write_node(child, summaries, base, child_dir)
        return

    # Non-root: write docs if leaf
    if node.is_leaf:
        _write_docs(node, node_dir)
    else:
        for child in node.children:
            child_local = child.dir_name or child.cluster_id
            child_dir = node_dir / child_local
            child_dir.mkdir(parents=True, exist_ok=True)
            _write_skill_md(child, summaries, child_dir)
            _write_node(child, summaries, base, child_dir)


def _write_skill_md(
    node: ClusterNode,
    summaries: dict[str, str],
    node_dir: Path,
) -> None:
    summary_body = summaries.get(node.cluster_id)
    if summary_body is not None:
        summary_body = _ensure_llm_summary_marker(summary_body)
    else:
        summary_body = _fallback_summary(node)
    frontmatter = "\n".join([
        "---",
        f"name: corpus/{node.cluster_id}",
        f"description: \"{node.label} ({node.total_docs} docs)\"",
        "user-invocable: false",
        "---",
        "",
        f"# {node.label}",
        "",
    ])
    (node_dir / "SKILL.md").write_text(
        frontmatter + summary_body + "\n", encoding="utf-8"
    )


def _write_docs(node: ClusterNode, node_dir: Path) -> None:
    docs_dir = node_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    for doc in node.documents:
        safe_name = _safe_filename(doc.doc_id + "_" + doc.title) + ".md"
        content = f"# {doc.title}\n\n**Type:** {doc.doc_type}  \n**Source:** {doc.source_path}\n\n{doc.text}\n"
        (docs_dir / safe_name).write_text(content, encoding="utf-8")


def _write_metadata(
    root: ClusterNode,
    config: Corpus2SkillConfig,
    stats: dict,
    base: Path,
) -> None:
    meta = {
        "corpus_name": config.output_name,
        "source_dir": str(config.source_dir),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "max_depth": config.max_depth,
            "min_cluster_size": config.min_cluster_size,
            "max_clusters_per_level": config.max_clusters_per_level,
            "model": config.model,
        },
        "stats": stats,
        "output_dir": str(base),
    }
    (base / "metadata.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _count_clusters(node: ClusterNode) -> int:
    if node.is_leaf:
        return 1
    return sum(_count_clusters(c) for c in node.children)


def _collect_types(node: ClusterNode, acc: dict[str, int], seen: set[tuple[str, str]]) -> None:
    for doc in node.documents:
        key = (doc.doc_id, str(doc.source_path))
        if key in seen:
            continue
        seen.add(key)
        acc[doc.doc_type] = acc.get(doc.doc_type, 0) + 1
    for child in node.children:
        _collect_types(child, acc, seen)


def _fallback_summary(node: ClusterNode) -> str:
    lines = [
        "## Overview",
        f"This cluster contains {len(node.documents)} document(s) related to: {node.label}.",
        "",
        "## Key Knowledge",
    ]
    for doc in node.documents[:5]:
        lines.append(f"- {doc.title} ({doc.doc_type})")
    return "\n".join(lines)


def _safe_filename(name: str) -> str:
    import re
    s = re.sub(r"[^\w\s-]", "", name)
    s = re.sub(r"[\s]+", "_", s.strip())
    return s[:60] or "document"


def _ensure_llm_summary_marker(summary_body: str) -> str:
    marker = "<!-- summary-source: llm -->"
    if marker in summary_body:
        return summary_body
    return f"{marker}\n{summary_body.lstrip()}"

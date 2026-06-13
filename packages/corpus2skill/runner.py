"""Main orchestrator for the Corpus2Skill pipeline."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.corpus2skill.config import Corpus2SkillConfig


def run_corpus2skill(config: Corpus2SkillConfig) -> dict:
    """
    Execute the full Corpus2Skill pipeline.

    Returns a stats dict with document counts, cluster counts, and output path.
    """
    from packages.corpus2skill.clusterer import build_hierarchy
    from packages.corpus2skill.embedder import TFIDFEmbedder
    from packages.corpus2skill.loader import load_documents
    from packages.corpus2skill.summarizer import summarize_cluster
    from packages.corpus2skill.writer import write_hierarchy

    # ── 1. Load ──────────────────────────────────────────────────────────────
    print(f"[C2S] Loading documents from {config.source_dir} ...", flush=True)
    docs = load_documents(config.source_dir)
    if not docs:
        print("[C2S] No documents found — nothing to process.")
        return {"status": "empty", "documents": 0}

    print(f"[C2S] Loaded {len(docs)} document(s)", flush=True)
    _print_type_breakdown(docs)

    # ── 2. Embed ─────────────────────────────────────────────────────────────
    print("[C2S] Building TF-IDF embeddings ...", flush=True)
    embedder = TFIDFEmbedder()
    matrix = embedder.fit_transform(docs)

    # ── 3. Cluster ───────────────────────────────────────────────────────────
    print("[C2S] Clustering documents ...", flush=True)
    root = build_hierarchy(docs, matrix, embedder, config)
    n_clusters = _count_clusters(root)
    print(f"[C2S] Built hierarchy: {n_clusters} cluster(s), depth <= {config.max_depth}", flush=True)

    # ── 4. Summarize ─────────────────────────────────────────────────────────
    print("[C2S] Generating cluster summaries with LLM ...", flush=True)
    summaries: dict[str, str] = {}
    if config.resume_summaries and config.skills_output_dir.exists():
        summaries = _load_existing_summaries(config.skills_output_dir)
        print(f"[C2S] Loaded {len(summaries)} existing summaries (resume mode)", flush=True)
    nodes_to_summarize = _collect_nodes(root)
    for i, node in enumerate(nodes_to_summarize, 1):
        if node.cluster_id in summaries:
            print(f"[C2S]   [{i}/{len(nodes_to_summarize)}] {node.cluster_id} (skipped)", flush=True)
            continue
        print(f"[C2S]   [{i}/{len(nodes_to_summarize)}] {node.cluster_id} ({len(node.documents)} docs)", flush=True)
        try:
            summaries[node.cluster_id] = summarize_cluster(node, config)
        except Exception as e:
            print(f"[C2S]   [WARN] Summarization failed for {node.cluster_id}: {e}", flush=True)

    # ── 5. Write ─────────────────────────────────────────────────────────────
    print(f"[C2S] Writing skill hierarchy to {config.skills_output_dir} ...", flush=True)
    stats = {
        "documents": len(docs),
        "clusters": n_clusters,
        "summaries_generated": len(summaries),
    }
    output_base = write_hierarchy(root, summaries, config, stats)

    print(f"\n{'='*60}")
    print(f"Corpus2Skill: {config.output_name}")
    print(f"{'='*60}")
    print(f"Documents:   {len(docs)}")
    print(f"Clusters:    {n_clusters}")
    print(f"Summaries:   {len(summaries)}")
    print(f"Output:      {output_base}")
    print(f"\nNavigate via: {output_base / 'INDEX.md'}")

    return {
        "status": "ok",
        "documents": len(docs),
        "clusters": n_clusters,
        "summaries_generated": len(summaries),
        "output_dir": str(output_base),
    }


def _print_type_breakdown(docs: list) -> None:
    counts: dict[str, int] = {}
    for d in docs:
        counts[d.doc_type] = counts.get(d.doc_type, 0) + 1
    parts = [f"{t}:{n}" for t, n in sorted(counts.items())]
    print(f"[C2S]   Types: {', '.join(parts)}", flush=True)


def _load_existing_summaries(output_dir: Path) -> dict:
    """Scan existing SKILL.md files and extract LLM-generated bodies."""
    import re
    summaries = {}
    for skill_file in output_dir.rglob("SKILL.md"):
        try:
            content = skill_file.read_text(encoding="utf-8")
            m = re.search(r"^name: corpus/(.+)$", content, re.MULTILINE)
            if not m:
                continue
            cluster_id = m.group(1).strip()
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue
            body = _strip_skill_header(parts[2])
            has_overview = "## Overview" in body
            if "<!-- summary-source: llm -->" in content and has_overview:
                summaries[cluster_id] = body
            elif has_overview and _looks_like_legacy_summary(body):
                summaries[cluster_id] = body
        except Exception:
            pass
    return summaries


def _looks_like_legacy_summary(body: str) -> bool:
    """Best-effort compatibility for pre-marker summaries without reviving known fallbacks."""
    if "## Key Knowledge" not in body:
        return False
    if _looks_like_generated_fallback(body):
        return False
    return "## When Useful" in body or "## Navigation" in body


def _looks_like_generated_fallback(body: str) -> bool:
    normalized = body.lstrip()
    known_prefixes = (
        "## Overview\nThis cluster contains ",
        "## Overview\nThis cluster groups ",
    )
    return normalized.startswith(known_prefixes)


def _strip_skill_header(body: str) -> str:
    lines = body.splitlines()
    header_idx = next(
        (i for i, line in enumerate(lines) if line.startswith("# ") and not line.startswith("## ")),
        None,
    )
    if header_idx is None:
        return body
    start = header_idx + 1
    while start < len(lines) and lines[start] == "":
        start += 1
    return "\n".join(lines[start:])


def _count_clusters(node) -> int:
    if node.is_leaf:
        return 1
    return sum(_count_clusters(c) for c in node.children)


def _collect_nodes(node) -> list:
    """Return all non-root nodes for summarization (BFS order)."""
    result = []
    queue = list(node.children) if node.children else [node]
    while queue:
        current = queue.pop(0)
        result.append(current)
        queue.extend(current.children)
    return result

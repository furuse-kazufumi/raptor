"""LLM-based cluster summarizer using claude-haiku."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.corpus2skill.clusterer import ClusterNode
    from packages.corpus2skill.config import Corpus2SkillConfig


_MAX_DOC_CHARS = 600
_MAX_CONTEXT_CHARS = 6000


def summarize_cluster(node: ClusterNode, config: Corpus2SkillConfig) -> str:
    """Generate SKILL.md body for this cluster node via claude-haiku."""
    context = _build_context(node)
    has_children = bool(node.children)
    nav_hint = _nav_hint(node) if has_children else ""

    prompt = f"""You are building a navigable skill directory for a security research LLM agent.

Analyze the following {len(node.documents)} document(s) in this cluster and produce a SKILL.md body.

Cluster label: {node.label}
Depth: {node.depth}

Documents (excerpts):
{context}

{nav_hint}

Write a SKILL.md body with these sections (no frontmatter — that will be added separately):

## Overview
2-3 sentences describing what this cluster covers.

## Key Knowledge
Bullet list of the most important security concepts, patterns, or findings in this cluster.

## When Useful
Bullet list of research questions or investigation scenarios where this cluster is relevant.
{_nav_section_template(node) if has_children else ""}

Keep the output concise and focused. Use markdown. Do not include frontmatter or the cluster_id."""

    return _call_llm(prompt, config.model)


def _build_context(node: ClusterNode) -> str:
    parts = []
    chars = 0
    for doc in node.documents:
        snippet = doc.text[:_MAX_DOC_CHARS].replace("\n", " ").strip()
        entry = f"[{doc.doc_type}] {doc.title}: {snippet}"
        if chars + len(entry) > _MAX_CONTEXT_CHARS:
            parts.append(f"... ({len(node.documents) - len(parts)} more documents)")
            break
        parts.append(entry)
        chars += len(entry)
    return "\n".join(parts)


def _nav_hint(node: ClusterNode) -> str:
    child_labels = [c.label for c in node.children]
    return (
        f"This cluster has {len(node.children)} sub-clusters: "
        + ", ".join(child_labels[:6])
        + ". Include a Navigation section listing them."
    )


def _nav_section_template(node: ClusterNode) -> str:
    lines = ["\n## Navigation"]
    for child in node.children:
        lines.append(f"- `{child.cluster_id}/SKILL.md` — {child.label}")
    return "\n".join(lines)


def _call_llm(prompt: str, model: str) -> str:
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "anthropic SDK is required: pip install anthropic"
        ) from exc

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text

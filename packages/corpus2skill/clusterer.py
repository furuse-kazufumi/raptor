"""K-means clustering with recursive hierarchy building."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from packages.corpus2skill.config import Corpus2SkillConfig
    from packages.corpus2skill.embedder import TFIDFEmbedder
    from packages.corpus2skill.loader import Document


_GENERIC_LABEL_TERMS = {
    "agent",
    "agents",
    "ai",
    "approach",
    "approaches",
    "based",
    "data",
    "framework",
    "method",
    "methods",
    "model",
    "models",
    "paper",
    "research",
    "results",
    "study",
    "system",
    "systems",
    "task",
    "tasks",
    "using",
}


@dataclass
class ClusterNode:
    cluster_id: str
    label: str
    documents: list[Document]
    children: list[ClusterNode] = field(default_factory=list)
    depth: int = 0
    dir_name: str = ""  # short local directory name for filesystem (never concatenated from parent)

    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0

    @property
    def total_docs(self) -> int:
        if self.is_leaf:
            return len(self.documents)
        return sum(c.total_docs for c in self.children)


def build_hierarchy(
    docs: list[Document],
    matrix: np.ndarray,
    embedder: TFIDFEmbedder,
    config: Corpus2SkillConfig,
    depth: int = 0,
    id_prefix: str = "",
) -> ClusterNode:
    """Recursively cluster documents into a hierarchy."""
    n = len(docs)

    if n <= config.min_cluster_size or depth >= config.max_depth:
        label = _make_label(docs, matrix, embedder, list(range(n)))
        node_id = id_prefix if id_prefix else "root"
        return ClusterNode(
            cluster_id=node_id,
            label=label,
            documents=docs,
            depth=depth,
        )

    k = _choose_k(n, config.max_clusters_per_level)

    try:
        from sklearn.cluster import KMeans
    except ImportError as exc:
        raise RuntimeError("scikit-learn is required: pip install scikit-learn") from exc

    km = KMeans(n_clusters=k, random_state=42, n_init="auto")
    labels = km.fit_predict(matrix)

    # Group documents by cluster label
    clusters: dict[int, list[int]] = {}
    for i, lbl in enumerate(labels):
        clusters.setdefault(int(lbl), []).append(i)

    root_label = _make_label(docs, matrix, embedder, list(range(n)))
    root_id = id_prefix if id_prefix else "root"
    root = ClusterNode(
        cluster_id=root_id,
        label=root_label,
        documents=docs,
        depth=depth,
    )

    for ci, (cluster_label_idx, indices) in enumerate(sorted(clusters.items())):
        cluster_docs = [docs[i] for i in indices]
        cluster_matrix = matrix[indices]
        # Numeric-only path to avoid label accumulation across recursion levels
        num_id = f"{id_prefix}_{ci:02d}" if id_prefix else f"{ci:02d}"
        term_label = _make_label(cluster_docs, matrix, embedder, indices)
        sanitized = _sanitize_label(term_label)

        # cluster_id uses numeric path + one level of label (for metadata/summaries key)
        child_id_full = f"cluster_{num_id}_{sanitized}"

        # dir_name: short LOCAL name, never concatenated from parent
        label_trunc = sanitized[:15] if depth == 0 else sanitized[:8]
        prefix = "cluster" if depth == 0 else "c"
        child_dir_name = f"{prefix}_{ci:02d}_{label_trunc}"

        should_recurse = (
            len(cluster_docs) > config.min_cluster_size * 2
            and depth + 1 < config.max_depth
        )

        if should_recurse:
            child = build_hierarchy(
                cluster_docs,
                cluster_matrix,
                embedder,
                config,
                depth=depth + 1,
                id_prefix=num_id,  # numeric only — prevents label concatenation
            )
            child.cluster_id = child_id_full
            child.dir_name = child_dir_name
            child.label = term_label
        else:
            child = ClusterNode(
                cluster_id=child_id_full,
                label=term_label,
                documents=cluster_docs,
                depth=depth + 1,
                dir_name=child_dir_name,
            )

        root.children.append(child)

    return root


def _choose_k(n: int, max_k: int) -> int:
    k = max(2, int(math.sqrt(n)))
    return min(k, max_k, n)


def _make_label(
    docs: list[Document],
    matrix: np.ndarray,
    embedder: TFIDFEmbedder,
    row_indices: list[int],
) -> str:
    candidates = embedder.top_terms_from_matrix(matrix, row_indices, n=12)
    terms = [term for term in candidates if _is_informative_label_term(term)][:3]
    if terms:
        return " / ".join(terms)
    # Fallback: use doc types
    types = list({d.doc_type for d in docs})
    return "-".join(types)


def _sanitize_label(label: str) -> str:
    s = re.sub(r"[^\w\s-]", "", label)
    s = re.sub(r"[\s/]+", "_", s.strip())
    return s[:40].strip("_").lower() or "misc"


def _is_informative_label_term(term: str) -> bool:
    normalized = term.strip().lower()
    if len(normalized) < 3:
        return False
    if normalized.isdigit():
        return False
    if normalized in _GENERIC_LABEL_TERMS:
        return False
    if re.fullmatch(r"\d+[a-z]*", normalized):
        return False
    return True

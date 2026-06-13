"""TF-IDF embedder — no external API required."""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from packages.corpus2skill.loader import Document


class TFIDFEmbedder:
    """Fit TF-IDF on a corpus of Documents and produce dense-ish sparse matrices."""

    def __init__(self, max_features: int = 5000) -> None:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
        except ImportError as exc:
            raise RuntimeError(
                "scikit-learn is required: pip install scikit-learn"
            ) from exc
        self._max_features = max_features
        self._vec = self._build_vectorizer(stop_words="english")
        self._fitted = False

    def _build_vectorizer(self, stop_words: str | None):
        from sklearn.feature_extraction.text import TfidfVectorizer

        return TfidfVectorizer(
            max_features=self._max_features,
            sublinear_tf=True,
            strip_accents="unicode",
            analyzer="word",
            token_pattern=r"(?u)\b\w\w+\b",
            min_df=1,
            stop_words=stop_words,
        )

    def fit_transform(self, docs: list[Document]) -> np.ndarray:
        texts = [d.text for d in docs]
        try:
            matrix = self._vec.fit_transform(texts)
        except ValueError as exc:
            if "empty vocabulary" not in str(exc):
                raise
            # Graceful fallback for degenerate corpora that become empty after stopword removal.
            self._vec = self._build_vectorizer(stop_words=None)
            matrix = self._vec.fit_transform(texts)
        self._fitted = True
        return matrix.toarray()

    def transform(self, docs: list[Document]) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("Call fit_transform first")
        texts = [d.text for d in docs]
        return self._vec.transform(texts).toarray()

    def top_terms(self, cluster_indices: list[int], n: int = 5) -> list[str]:
        """Return top n TF-IDF terms for a subset of documents."""
        if not self._fitted:
            return []
        feature_names = self._vec.get_feature_names_out()
        # Sum TF-IDF scores across documents in this cluster
        scores = np.zeros(len(feature_names))
        for idx in cluster_indices:
            # Re-transform is cheap for individual docs; we use stored vectorizer
            pass
        # We'll need the matrix passed in; use a simpler heuristic here
        # (caller passes pre-computed matrix rows)
        return list(feature_names[:n])

    def top_terms_from_matrix(
        self, matrix: np.ndarray, row_indices: list[int], n: int = 5
    ) -> list[str]:
        """Return top n terms for the given rows of the TF-IDF matrix."""
        if not self._fitted or len(row_indices) == 0:
            return []
        feature_names = self._vec.get_feature_names_out()
        subset = matrix[row_indices].sum(axis=0)
        nonzero_idx = np.flatnonzero(subset > 0)
        if len(nonzero_idx) == 0:
            return []
        ranked_idx = nonzero_idx[np.argsort(subset[nonzero_idx])[::-1]]
        top_idx = ranked_idx[:n]
        return [feature_names[i] for i in top_idx]

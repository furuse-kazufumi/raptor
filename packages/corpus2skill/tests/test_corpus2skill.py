"""Unit tests for the corpus2skill package."""
import json
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure RAPTOR root is on sys.path
_RAPTOR_ROOT = Path(__file__).resolve().parents[3]
if str(_RAPTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_RAPTOR_ROOT))


# ── loader tests ──────────────────────────────────────────────────────────────

class TestLoader:
    def test_load_markdown(self, tmp_path):
        from packages.corpus2skill.loader import load_documents
        (tmp_path / "guide.md").write_text("# Security Guide\n\nThis covers XSS attacks.", encoding="utf-8")
        docs = load_documents(tmp_path)
        assert len(docs) == 1
        assert docs[0].doc_type == "markdown"
        assert docs[0].title == "Security Guide"
        assert "XSS" in docs[0].text

    def test_load_text_file(self, tmp_path):
        from packages.corpus2skill.loader import load_documents
        (tmp_path / "notes.txt").write_text("Buffer overflow in function foo", encoding="utf-8")
        docs = load_documents(tmp_path)
        assert len(docs) == 1
        assert docs[0].doc_type == "markdown"

    def test_load_raptor_findings_list(self, tmp_path):
        from packages.corpus2skill.loader import load_documents
        findings = [
            {"title": "SQL Injection", "severity": "high", "description": "User input not sanitized"},
            {"title": "XSS", "severity": "medium", "description": "Reflected XSS in search"},
        ]
        (tmp_path / "findings.json").write_text(json.dumps(findings), encoding="utf-8")
        docs = load_documents(tmp_path)
        assert len(docs) == 1
        assert docs[0].doc_type == "findings"
        assert "SQL Injection" in docs[0].text

    def test_load_raptor_findings_dict(self, tmp_path):
        from packages.corpus2skill.loader import load_documents
        data = {"target": "myapp", "findings": [
            {"title": "RCE", "severity": "critical", "description": "Remote code execution"}
        ]}
        (tmp_path / "report.json").write_text(json.dumps(data), encoding="utf-8")
        docs = load_documents(tmp_path)
        assert len(docs) == 1
        assert docs[0].doc_type == "findings"

    def test_load_cve_osv_format(self, tmp_path):
        from packages.corpus2skill.loader import load_documents
        cve = {"id": "CVE-2024-1234", "summary": "Critical buffer overflow", "details": "Details here"}
        (tmp_path / "cve.json").write_text(json.dumps(cve), encoding="utf-8")
        docs = load_documents(tmp_path)
        assert len(docs) == 1
        assert docs[0].doc_type == "cve"
        assert docs[0].title == "CVE-2024-1234"

    def test_load_source_code(self, tmp_path):
        from packages.corpus2skill.loader import load_documents
        (tmp_path / "vuln.py").write_text("def handle_input(data):\n    eval(data)  # dangerous\n", encoding="utf-8")
        docs = load_documents(tmp_path)
        assert len(docs) == 1
        assert docs[0].doc_type == "code"

    def test_skips_empty_files(self, tmp_path):
        from packages.corpus2skill.loader import load_documents
        (tmp_path / "empty.md").write_text("   \n  ", encoding="utf-8")
        docs = load_documents(tmp_path)
        assert len(docs) == 0

    def test_skips_git_dir(self, tmp_path):
        from packages.corpus2skill.loader import load_documents
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("git config content", encoding="utf-8")
        (tmp_path / "readme.md").write_text("# Real doc", encoding="utf-8")
        docs = load_documents(tmp_path)
        assert len(docs) == 1

    def test_mixed_sources(self, tmp_path):
        from packages.corpus2skill.loader import load_documents
        (tmp_path / "notes.md").write_text("# XSS Notes\n\nContent", encoding="utf-8")
        (tmp_path / "code.py").write_text("import os\nos.system(input())", encoding="utf-8")
        cve = {"id": "CVE-2023-9999", "summary": "Test CVE"}
        (tmp_path / "cve.json").write_text(json.dumps(cve), encoding="utf-8")
        docs = load_documents(tmp_path)
        assert len(docs) == 3
        types = {d.doc_type for d in docs}
        assert "markdown" in types
        assert "code" in types
        assert "cve" in types


# ── config tests ──────────────────────────────────────────────────────────────

class TestConfig:
    def test_defaults(self, tmp_path):
        from packages.corpus2skill.config import Corpus2SkillConfig
        cfg = Corpus2SkillConfig(source_dir=tmp_path, output_name="test")
        assert cfg.max_depth == 2
        assert cfg.min_cluster_size == 3
        assert cfg.max_clusters_per_level == 8
        assert cfg.model == "claude-haiku-4-5-20251001"
        assert not cfg.overwrite

    def test_skills_output_dir(self, tmp_path):
        from packages.corpus2skill.config import Corpus2SkillConfig
        cfg = Corpus2SkillConfig(source_dir=tmp_path, output_name="mytest", raptor_dir=tmp_path)
        expected = tmp_path / ".claude" / "skills" / "corpus" / "mytest"
        assert cfg.skills_output_dir == expected

    def test_source_dir_resolved(self, tmp_path):
        from packages.corpus2skill.config import Corpus2SkillConfig
        cfg = Corpus2SkillConfig(source_dir=tmp_path, output_name="test")
        assert cfg.source_dir.is_absolute()


# ── embedder tests ────────────────────────────────────────────────────────────

class TestEmbedder:
    pytest.importorskip("sklearn", reason="scikit-learn not installed")

    def test_fit_transform_shape(self, tmp_path):
        from packages.corpus2skill.embedder import TFIDFEmbedder
        from packages.corpus2skill.loader import Document
        docs = [
            Document("d0", tmp_path / "a.md", "markdown", "Title A", "security vulnerability buffer overflow"),
            Document("d1", tmp_path / "b.md", "markdown", "Title B", "sql injection web attack"),
            Document("d2", tmp_path / "c.md", "cve", "CVE-2024-1", "remote code execution critical"),
        ]
        emb = TFIDFEmbedder(max_features=100)
        matrix = emb.fit_transform(docs)
        assert matrix.shape == (3, min(100, matrix.shape[1]))

    def test_top_terms_from_matrix(self, tmp_path):
        from packages.corpus2skill.embedder import TFIDFEmbedder
        from packages.corpus2skill.loader import Document
        docs = [
            Document("d0", tmp_path / "a.md", "markdown", "A", "buffer overflow memory corruption heap"),
            Document("d1", tmp_path / "b.md", "markdown", "B", "sql injection database query"),
        ]
        emb = TFIDFEmbedder(max_features=50)
        matrix = emb.fit_transform(docs)
        terms = emb.top_terms_from_matrix(matrix, [0], n=3)
        assert len(terms) <= 3
        assert all(isinstance(t, str) for t in terms)


# ── clusterer tests ───────────────────────────────────────────────────────────

class TestClusterer:
    pytest.importorskip("sklearn", reason="scikit-learn not installed")

    def _make_docs(self, n: int, tmp_path: Path):
        from packages.corpus2skill.loader import Document
        topics = [
            "buffer overflow memory corruption heap stack",
            "sql injection database query input",
            "xss cross site scripting web browser",
        ]
        return [
            Document(f"d{i:03d}", tmp_path / f"d{i}.md", "markdown", f"Doc {i}",
                     topics[i % len(topics)] + f" extra{i}")
            for i in range(n)
        ]

    def test_small_corpus_is_leaf(self, tmp_path):
        from packages.corpus2skill.clusterer import build_hierarchy
        from packages.corpus2skill.config import Corpus2SkillConfig
        from packages.corpus2skill.embedder import TFIDFEmbedder

        docs = self._make_docs(3, tmp_path)
        cfg = Corpus2SkillConfig(source_dir=tmp_path, output_name="t", min_cluster_size=5)
        emb = TFIDFEmbedder(max_features=50)
        matrix = emb.fit_transform(docs)
        root = build_hierarchy(docs, matrix, emb, cfg)
        assert root.is_leaf

    def test_large_corpus_has_children(self, tmp_path):
        from packages.corpus2skill.clusterer import build_hierarchy
        from packages.corpus2skill.config import Corpus2SkillConfig
        from packages.corpus2skill.embedder import TFIDFEmbedder

        docs = self._make_docs(12, tmp_path)
        cfg = Corpus2SkillConfig(source_dir=tmp_path, output_name="t",
                                  min_cluster_size=2, max_clusters_per_level=4)
        emb = TFIDFEmbedder(max_features=50)
        matrix = emb.fit_transform(docs)
        root = build_hierarchy(docs, matrix, emb, cfg)
        assert not root.is_leaf
        assert len(root.children) >= 2

    def test_total_docs_preserved(self, tmp_path):
        from packages.corpus2skill.clusterer import build_hierarchy
        from packages.corpus2skill.config import Corpus2SkillConfig
        from packages.corpus2skill.embedder import TFIDFEmbedder

        n = 9
        docs = self._make_docs(n, tmp_path)
        cfg = Corpus2SkillConfig(source_dir=tmp_path, output_name="t",
                                  min_cluster_size=2, max_clusters_per_level=3)
        emb = TFIDFEmbedder(max_features=50)
        matrix = emb.fit_transform(docs)
        root = build_hierarchy(docs, matrix, emb, cfg)
        assert root.total_docs == n

    def test_max_depth_respected(self, tmp_path):
        from packages.corpus2skill.clusterer import build_hierarchy, ClusterNode
        from packages.corpus2skill.config import Corpus2SkillConfig
        from packages.corpus2skill.embedder import TFIDFEmbedder

        docs = self._make_docs(20, tmp_path)
        cfg = Corpus2SkillConfig(source_dir=tmp_path, output_name="t",
                                  min_cluster_size=2, max_depth=1)
        emb = TFIDFEmbedder(max_features=50)
        matrix = emb.fit_transform(docs)
        root = build_hierarchy(docs, matrix, emb, cfg)

        def max_depth(node: ClusterNode) -> int:
            if node.is_leaf:
                return node.depth
            return max(max_depth(c) for c in node.children)

        assert max_depth(root) <= 1


# ── writer tests ──────────────────────────────────────────────────────────────

class TestWriter:
    def _make_leaf_root(self, tmp_path: Path):
        from packages.corpus2skill.clusterer import ClusterNode
        from packages.corpus2skill.loader import Document
        docs = [
            Document("d0", tmp_path / "a.md", "markdown", "Doc A", "security content"),
            Document("d1", tmp_path / "b.json", "cve", "CVE-2024-1", "vuln description"),
        ]
        return ClusterNode(cluster_id="root", label="security / cve", documents=docs)

    def test_writes_index_and_metadata(self, tmp_path):
        from packages.corpus2skill.config import Corpus2SkillConfig
        from packages.corpus2skill.writer import write_hierarchy

        root = self._make_leaf_root(tmp_path)
        cfg = Corpus2SkillConfig(source_dir=tmp_path, output_name="test_write",
                                  raptor_dir=tmp_path)
        output_base = write_hierarchy(root, {}, cfg, {"documents": 2})

        assert (output_base / "INDEX.md").exists()
        assert (output_base / "metadata.json").exists()

    def test_metadata_content(self, tmp_path):
        from packages.corpus2skill.config import Corpus2SkillConfig
        from packages.corpus2skill.writer import write_hierarchy

        root = self._make_leaf_root(tmp_path)
        cfg = Corpus2SkillConfig(source_dir=tmp_path, output_name="test_meta",
                                  raptor_dir=tmp_path)
        output_base = write_hierarchy(root, {}, cfg, {"documents": 2})

        meta = json.loads((output_base / "metadata.json").read_text())
        assert meta["corpus_name"] == "test_meta"
        assert meta["stats"]["documents"] == 2

    def test_index_lists_clusters(self, tmp_path):
        from packages.corpus2skill.clusterer import ClusterNode
        from packages.corpus2skill.config import Corpus2SkillConfig
        from packages.corpus2skill.loader import Document
        from packages.corpus2skill.writer import write_hierarchy

        docs = [Document("d0", tmp_path / "a.md", "markdown", "A", "content")]
        child1 = ClusterNode("cluster_00_web", "web attacks", docs)
        child2 = ClusterNode("cluster_01_memory", "memory bugs", docs)
        root = ClusterNode("root", "all", docs, children=[child1, child2])

        cfg = Corpus2SkillConfig(source_dir=tmp_path, output_name="test_idx",
                                  raptor_dir=tmp_path)
        output_base = write_hierarchy(root, {}, cfg, {})

        index_text = (output_base / "INDEX.md").read_text(encoding="utf-8")
        assert "cluster_00_web" in index_text
        assert "cluster_01_memory" in index_text

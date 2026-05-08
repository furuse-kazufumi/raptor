#!/usr/bin/env python3
"""Drive 4-domain RAD expansion sequentially.

After BG-1 (security_papers fetch) finishes, run this to populate
agents_corpus / llm_corpus / vllm_corpus / security_corpus with arXiv
papers, then trigger corpus2skill on each.

Sequential execution avoids arXiv rate-limit collisions.
"""
import os
import subprocess
import sys
from pathlib import Path

DOMAINS = ["agents", "llm", "vllm", "security"]
PER_QUERY = 120          # ~1200 papers per domain (10 queries × 120)
SINCE = "2022-01-01"
ROOT = Path(__file__).parent
CORPUS_BASE = ROOT / ".claude" / "skills" / "corpus"


def run(cmd, **kwargs):
    print(f"\n[drive] $ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, check=False, **kwargs)


def fetch_domain(domain: str) -> Path:
    corpus_dir = CORPUS_BASE / f"{domain}_corpus"
    queries_file = corpus_dir / "arxiv_queries.txt"
    papers_dir = corpus_dir / "papers"

    if not queries_file.exists():
        print(f"[drive] SKIP {domain}: no arxiv_queries.txt", flush=True)
        return None

    papers_dir.mkdir(exist_ok=True)
    print(f"\n[drive] === FETCH {domain} ===", flush=True)
    run([
        sys.executable, "fetch_arxiv_topical.py",
        "--query-file", str(queries_file),
        "--output", str(papers_dir),
        "--per-query", str(PER_QUERY),
        "--since", SINCE,
    ], cwd=ROOT)

    n = len(list(papers_dir.glob("*.md")))
    print(f"[drive] {domain}: {n} papers in {papers_dir}", flush=True)
    return papers_dir if n >= 30 else None


def corpus2skill(papers_dir: Path, name: str):
    print(f"\n[drive] === CORPUS2SKILL {name} ===", flush=True)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    run([
        sys.executable, "raptor_corpus2skill.py",
        "--source", str(papers_dir),
        "--name", name,
        "--overwrite",
        "--max-depth", "2",
        "--min-cluster-size", "5",
        "--max-clusters", "8",
    ], cwd=ROOT, env=env)


def main():
    populated = []
    for d in DOMAINS:
        papers = fetch_domain(d)
        if papers is not None:
            populated.append((d, papers))

    print("\n[drive] === FETCH PHASE DONE ===", flush=True)
    print(f"[drive] Populated domains: {[d for d, _ in populated]}", flush=True)

    # Skill rebuild — each domain gets a separate skill name to avoid clobbering
    for d, papers in populated:
        corpus2skill(papers, f"{d}_corpus_v2")

    print("\n[drive] === ALL DONE ===", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)

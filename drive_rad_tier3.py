#!/usr/bin/env python3
"""Drive Tier-3 RAD expansion (13 remaining stub domains, sequential)."""
import os
import subprocess
import sys
import time
from pathlib import Path

DOMAINS = [
    "deep_learning", "neural_network", "diffusion", "optimization",
    "statistics", "robotics", "quantum_computing", "automotive",
    "infrastructure", "multivariate_analysis", "numerical_methods",
    "information_theory", "game_dev",
]
PER_QUERY = 80
SINCE = "2022-01-01"
ROOT = Path(__file__).parent
CORPUS_BASE = ROOT / ".claude" / "skills" / "corpus"


def run(cmd):
    print(f"\n[drive3] $ {' '.join(cmd)}", flush=True)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(cmd, check=False, env=env)


def fetch_domain(domain):
    corpus_dir = CORPUS_BASE / f"{domain}_corpus"
    queries_file = corpus_dir / "arxiv_queries.txt"
    papers_dir = corpus_dir / "papers"
    if not queries_file.exists():
        print(f"[drive3] SKIP {domain}: no arxiv_queries.txt", flush=True)
        return 0
    papers_dir.mkdir(exist_ok=True)
    print(f"\n[drive3] === FETCH {domain} ===", flush=True)
    run([
        sys.executable, "fetch_arxiv_topical.py",
        "--query-file", str(queries_file),
        "--output", str(papers_dir),
        "--per-query", str(PER_QUERY),
        "--since", SINCE,
    ])
    n = len(list(papers_dir.glob("*.md")))
    print(f"[drive3] {domain}: {n} papers", flush=True)
    # Cool-down between domains to avoid arXiv throttling
    time.sleep(15)
    return n


def main():
    totals = {}
    for d in DOMAINS:
        totals[d] = fetch_domain(d)
    print("\n[drive3] === FETCH PHASE DONE ===", flush=True)
    print(f"[drive3] Per-domain counts: {totals}", flush=True)
    print(f"[drive3] Grand total: {sum(totals.values())} papers", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)

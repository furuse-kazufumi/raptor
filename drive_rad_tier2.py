#!/usr/bin/env python3
"""Drive Tier-2 RAD expansion (image, mlops, industrial_iot, medical)."""
import os
import subprocess
import sys
from pathlib import Path

DOMAINS = ["image", "mlops", "industrial_iot", "medical"]
PER_QUERY = 100
SINCE = "2022-01-01"
ROOT = Path(__file__).parent
CORPUS_BASE = ROOT / ".claude" / "skills" / "corpus"


def run(cmd):
    print(f"\n[drive2] $ {' '.join(cmd)}", flush=True)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(cmd, check=False, env=env)


def fetch_domain(domain):
    corpus_dir = CORPUS_BASE / f"{domain}_corpus"
    queries_file = corpus_dir / "arxiv_queries.txt"
    papers_dir = corpus_dir / "papers"
    if not queries_file.exists():
        print(f"[drive2] SKIP {domain}: no arxiv_queries.txt", flush=True)
        return
    papers_dir.mkdir(exist_ok=True)
    print(f"\n[drive2] === FETCH {domain} ===", flush=True)
    run([
        sys.executable, "fetch_arxiv_topical.py",
        "--query-file", str(queries_file),
        "--output", str(papers_dir),
        "--per-query", str(PER_QUERY),
        "--since", SINCE,
    ])
    n = len(list(papers_dir.glob("*.md")))
    print(f"[drive2] {domain}: {n} papers in {papers_dir}", flush=True)


def main():
    for d in DOMAINS:
        fetch_domain(d)
    print("\n[drive2] === FETCH PHASE DONE ===", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)

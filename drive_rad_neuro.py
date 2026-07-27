#!/usr/bin/env python3
"""Drive RAD neuro expansion (8 BCI/neuroscience domains, sequential).

Pipeline per domain:
1. fetch_arxiv_topical.py  --query-file C:/dev/docs/<dom>_corpus/arxiv_queries.txt
                           --output C:/dev/docs/<dom>_corpus/papers
2. raptor_corpus2skill.py  --source C:/dev/docs/<dom>_corpus/papers
                           --name <dom>_corpus_v2
   (writes to C:/.../.claude/skills/corpus/<dom>_corpus_v2/)
3. Move that hierarchy to C:/dev/docs/<dom>_corpus_v2/  (D-drive policy)
4. Cool-down between fetches to avoid arXiv 429
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

DOMAINS = [
    "bci", "neuroscience", "neural_signal", "neural_prosthetics",
    "cognitive_ai", "neuromorphic", "neural_dataset", "neuro_ethics",
]
PER_QUERY = 80
SINCE = "2022-01-01"
ROOT = Path(__file__).parent
DOCS_BASE = Path("C:/dev/docs")
SKILLS_CORPUS = ROOT / ".claude" / "skills" / "corpus"


def run(cmd, cwd=None):
    print(f"\n[neuro] $ {' '.join(map(str, cmd))}", flush=True)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(cmd, check=False, env=env, cwd=cwd)


def fetch_domain(domain):
    corpus_dir = DOCS_BASE / f"{domain}_corpus"
    queries_file = corpus_dir / "arxiv_queries.txt"
    papers_dir = corpus_dir / "papers"
    if not queries_file.exists():
        print(f"[neuro] SKIP {domain}: no arxiv_queries.txt at {queries_file}", flush=True)
        return 0
    papers_dir.mkdir(exist_ok=True)
    print(f"\n[neuro] === FETCH {domain} ===", flush=True)
    run([
        sys.executable, str(ROOT / "fetch_arxiv_topical.py"),
        "--query-file", str(queries_file),
        "--output", str(papers_dir),
        "--per-query", str(PER_QUERY),
        "--since", SINCE,
    ])
    n = len(list(papers_dir.glob("*.md")))
    print(f"[neuro] {domain}: {n} papers fetched", flush=True)
    return n


def corpus2skill_domain(domain):
    corpus_dir = DOCS_BASE / f"{domain}_corpus"
    papers_dir = corpus_dir / "papers"
    name = f"{domain}_corpus_v2"
    skill_out = SKILLS_CORPUS / name
    final_out = DOCS_BASE / name

    if not papers_dir.exists() or not list(papers_dir.glob("*.md")):
        print(f"[neuro] SKIP corpus2skill {domain}: no papers", flush=True)
        return False

    if final_out.exists():
        print(f"[neuro] {domain}: removing existing {final_out}", flush=True)
        shutil.rmtree(final_out)

    print(f"\n[neuro] === CORPUS2SKILL {domain} ===", flush=True)
    rc = run([
        "py", "-3.11", str(ROOT / "raptor_corpus2skill.py"),
        "--source", str(papers_dir),
        "--name", name,
        "--overwrite",
        "--max-depth", "2",
        "--min-cluster-size", "5",
        "--max-clusters", "8",
    ], cwd=str(ROOT))
    if rc.returncode != 0:
        print(f"[neuro] FAIL corpus2skill {domain} rc={rc.returncode}", flush=True)
        return False

    if not skill_out.exists():
        print(f"[neuro] WARN: expected output not found at {skill_out}", flush=True)
        return False

    print(f"[neuro] move {skill_out} -> {final_out}", flush=True)
    shutil.move(str(skill_out), str(final_out))
    return True


def main():
    print(f"[neuro] start: {len(DOMAINS)} domains, per-query={PER_QUERY}, since={SINCE}", flush=True)

    # Phase 1: fetch all domains sequentially (arXiv rate-limited)
    fetched = {}
    for d in DOMAINS:
        n = fetch_domain(d)
        fetched[d] = n
        time.sleep(15)
    print(f"\n[neuro] === FETCH PHASE DONE ===", flush=True)
    print(f"[neuro] Per-domain papers: {fetched}", flush=True)
    print(f"[neuro] Grand total fetched: {sum(fetched.values())}", flush=True)

    # Phase 2: corpus2skill each domain (claude-haiku API; serial for budget control)
    skilled = []
    for d in DOMAINS:
        if fetched.get(d, 0) == 0:
            print(f"[neuro] skip corpus2skill {d}: 0 papers", flush=True)
            continue
        ok = corpus2skill_domain(d)
        if ok:
            skilled.append(d)

    print(f"\n[neuro] === ALL DONE ===", flush=True)
    print(f"[neuro] fetched: {fetched}", flush=True)
    print(f"[neuro] hierarchy built: {skilled}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)

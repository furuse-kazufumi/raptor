#!/usr/bin/env python3
"""Fetch new RAD corpora from arXiv for skill-cache differentiation.

Outputs to D:/docs/<corpus>_v2/ as one .md file per paper (title + abstract + meta).
"""

from __future__ import annotations
import time
import re
import sys
from pathlib import Path
import arxiv

DOCS_ROOT = Path("D:/docs")
MAX_RESULTS = 200  # per category

CORPORA: dict[str, list[str]] = {
    "astrophysics_corpus_v2": [
        "astro-ph.GA", "astro-ph.SR", "astro-ph.HE",
        "astro-ph.CO", "astro-ph.EP", "astro-ph.IM",
    ],
    "aerospace_corpus_v2": [
        "physics.flu-dyn",      # 流体力学
        "eess.SY",              # 制御システム
        "cs.RO",                # ロボティクス（一部宇宙ロボ）
    ],
    "satellite_engineering_corpus_v2": [
        "physics.space-ph",     # 宇宙物理
        "eess.SP",              # 信号処理（衛星通信）
        "cs.NI",                # ネットワーク（衛星リンク）
    ],
    "reinforcement_learning_corpus_v2": [
        "cs.LG",                # Machine Learning（RL filter は title で）
        "cs.AI",
        "stat.ML",
    ],
    "hci_corpus_v2": [
        "cs.HC",                # Human-Computer Interaction
    ],
    "formal_methods_corpus_v2": [
        "cs.LO",                # Logic in CS
        "cs.PL",                # Programming Languages
        "cs.SE",                # Software Engineering
    ],
    "multimodal_corpus_v2": [
        "cs.CV",                # Computer Vision
        "cs.MM",                # Multimedia
        "cs.CL",                # Computation and Language
    ],
    "distributed_systems_corpus_v2": [
        "cs.DC",                # Distributed/Parallel Computing
    ],
}

# RL filter keywords for cs.LG/cs.AI to narrow down
RL_FILTERS = re.compile(
    r"\b(reinforcement learning|RLHF|policy gradient|actor[- ]critic|Q[- ]learning|bandit|MDP)\b",
    re.IGNORECASE,
)
MULTIMODAL_FILTERS = re.compile(
    r"\b(multi[- ]?modal|vision[- ]language|text[- ]to[- ]image|video[- ]language|cross[- ]modal)\b",
    re.IGNORECASE,
)


def sanitize(s: str) -> str:
    s = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", s)
    return s.strip()[:100]


def fetch(corpus: str, categories: list[str]) -> int:
    out = DOCS_ROOT / corpus
    out.mkdir(parents=True, exist_ok=True)
    seen: set[str] = {p.stem for p in out.glob("*.md")}
    client = arxiv.Client(page_size=100, delay_seconds=3, num_retries=3)
    written = 0
    for cat in categories:
        print(f"  [{corpus}] cat={cat} ...", flush=True)
        search = arxiv.Search(
            query=f"cat:{cat}",
            max_results=MAX_RESULTS,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )
        try:
            for r in client.results(search):
                title = r.title or ""
                summary = r.summary or ""
                # 軽いフィルタ
                if corpus == "reinforcement_learning_corpus_v2":
                    if not (RL_FILTERS.search(title) or RL_FILTERS.search(summary)):
                        continue
                if corpus == "multimodal_corpus_v2":
                    if not (MULTIMODAL_FILTERS.search(title) or MULTIMODAL_FILTERS.search(summary)):
                        continue
                arxiv_id = r.entry_id.split("/")[-1].split("v")[0]
                if arxiv_id in seen:
                    continue
                seen.add(arxiv_id)
                fname = sanitize(f"{arxiv_id}_{title}") + ".md"
                authors = ", ".join(str(a) for a in r.authors[:5])
                body = (
                    f"# {title}\n\n"
                    f"- **arXiv ID:** {arxiv_id}\n"
                    f"- **Authors:** {authors}\n"
                    f"- **Categories:** {', '.join(r.categories)}\n"
                    f"- **Published:** {r.published.isoformat() if r.published else 'unknown'}\n"
                    f"- **URL:** {r.entry_id}\n\n"
                    f"## Abstract\n\n{summary}\n"
                )
                (out / fname).write_text(body, encoding="utf-8")
                written += 1
        except Exception as e:
            print(f"    ERROR {cat}: {e}", flush=True)
        time.sleep(3)  # arXiv API politeness between categories
    return written


def main() -> int:
    total = 0
    for corpus, cats in CORPORA.items():
        print(f"=== {corpus} ===", flush=True)
        n = fetch(corpus, cats)
        print(f"  wrote {n} files\n", flush=True)
        total += n
    print(f"DONE: {total} total files written across {len(CORPORA)} corpora")
    return 0


if __name__ == "__main__":
    sys.exit(main())

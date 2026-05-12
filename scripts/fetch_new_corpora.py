#!/usr/bin/env python3
"""Fetch new RAD corpora from arXiv for skill-cache differentiation (overnight run).

Outputs to D:/docs/<corpus>/ as one .md file per paper (title + abstract + meta).
Idempotent: skips already-fetched arxiv_id.
"""

from __future__ import annotations
import time
import re
import sys
from pathlib import Path
import arxiv

DOCS_ROOT = Path("D:/docs")
MAX_RESULTS = 800  # per category
SLEEP_BETWEEN_CATS = 3

# Filter regexes for narrowing broad categories
RL_FILTER = re.compile(
    r"\b(reinforcement learning|RLHF|policy gradient|actor[- ]critic|Q[- ]learning|bandit|MDP|offline RL|model[- ]based RL)\b",
    re.IGNORECASE,
)
MULTIMODAL_FILTER = re.compile(
    r"\b(multi[- ]?modal|vision[- ]language|text[- ]to[- ]image|video[- ]language|cross[- ]modal|audio[- ]visual)\b",
    re.IGNORECASE,
)
INDUSTRIAL_FILTER = re.compile(
    r"\b(OPC[- ]UA|Modbus|MQTT|BACnet|EtherCAT|PROFINET|industrial IoT|SCADA|IIoT|fieldbus|industrial protocol|industrial control)\b",
    re.IGNORECASE,
)
GAME_AI_FILTER = re.compile(
    r"\b(chess|shogi|go (game|board)|AlphaGo|AlphaZero|MuZero|poker|mahjong|StarCraft|Dota|game playing|self[- ]play|MCTS|game AI)\b",
    re.IGNORECASE,
)
TIME_SERIES_FILTER = re.compile(
    r"\b(time[- ]series|temporal|forecasting|ARIMA|LSTM forecast|transformer forecast|seasonal|autoregressive)\b",
    re.IGNORECASE,
)
TINYML_FILTER = re.compile(
    r"\b(TinyML|tiny ML|edge ML|edge AI|on[- ]device|microcontroller|MCU|embedded ML|TFLite|quantization|pruning|knowledge distillation)\b",
    re.IGNORECASE,
)
ATP_FILTER = re.compile(
    r"\b(Lean|Coq|Isabelle|TLA\+|Agda|theorem prov|formal verif|SMT solver|SAT solver|proof assistant|automated reasoning)\b",
    re.IGNORECASE,
)


CORPORA: list[tuple[str, list[str], re.Pattern | None]] = [
    # Space cluster
    ("astrophysics_corpus_v2", ["astro-ph.GA", "astro-ph.SR", "astro-ph.HE",
                                 "astro-ph.CO", "astro-ph.EP", "astro-ph.IM"], None),
    ("aerospace_corpus_v2", ["physics.flu-dyn", "eess.SY", "cs.RO"], None),
    ("satellite_engineering_corpus_v2", ["physics.space-ph", "eess.SP", "cs.NI"], None),
    # AI / ML cluster
    ("reinforcement_learning_corpus_v2", ["cs.LG", "cs.AI", "stat.ML"], RL_FILTER),
    ("multimodal_corpus_v2", ["cs.CV", "cs.MM", "cs.CL"], MULTIMODAL_FILTER),
    ("game_ai_corpus_v2", ["cs.AI", "cs.LG"], GAME_AI_FILTER),
    ("time_series_corpus_v2", ["stat.ML", "cs.LG", "stat.AP"], TIME_SERIES_FILTER),
    ("tinyml_corpus_v2", ["cs.LG", "cs.AR"], TINYML_FILTER),
    # Systems / SE cluster
    ("hci_corpus_v2", ["cs.HC"], None),
    ("formal_methods_corpus_v2", ["cs.LO", "cs.PL", "cs.SE"], None),
    ("distributed_systems_corpus_v2", ["cs.DC"], None),
    ("compiler_corpus_v2", ["cs.PL"], None),
    ("cryptography_corpus_v2", ["cs.CR"], None),
    ("automated_theorem_proving_corpus_v2", ["cs.LO", "cs.AI"], ATP_FILTER),
    # Industrial / IoT
    ("industrial_protocols_corpus_v2", ["cs.NI", "eess.SY"], INDUSTRIAL_FILTER),
    # Bio / science
    ("protein_corpus_v2", ["q-bio.BM", "q-bio.MN", "q-bio.QM"], None),
]


def sanitize(s: str) -> str:
    s = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", s)
    return s.strip()[:100]


def fetch(corpus: str, categories: list[str], filter_re: re.Pattern | None) -> int:
    out = DOCS_ROOT / corpus
    out.mkdir(parents=True, exist_ok=True)
    seen: set[str] = {p.stem.split("_")[0] for p in out.glob("*.md")}
    client = arxiv.Client(page_size=100, delay_seconds=3, num_retries=3)
    written = 0
    for cat in categories:
        print(f"  [{corpus}] cat={cat} (already have {len(seen)}) ...", flush=True)
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
                if filter_re is not None:
                    if not (filter_re.search(title) or filter_re.search(summary)):
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
                try:
                    (out / fname).write_text(body, encoding="utf-8")
                    written += 1
                except OSError as e:
                    print(f"    write skip: {e}", flush=True)
        except Exception as e:
            print(f"    ERROR {cat}: {e}", flush=True)
        time.sleep(SLEEP_BETWEEN_CATS)
    return written


def main() -> int:
    total = 0
    for corpus, cats, filter_re in CORPORA:
        print(f"=== {corpus} ===", flush=True)
        try:
            n = fetch(corpus, cats, filter_re)
            print(f"  wrote {n} new files\n", flush=True)
            total += n
        except KeyboardInterrupt:
            print("  interrupted", flush=True)
            return 1
        except Exception as e:
            print(f"  CORPUS ERROR: {e}\n", flush=True)
    print(f"DONE: {total} total new files across {len(CORPORA)} corpora")
    return 0


if __name__ == "__main__":
    sys.exit(main())

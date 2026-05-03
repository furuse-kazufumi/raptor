#!/usr/bin/env python3
"""
Large-scale security corpus fetcher (~36,000 documents overnight).

Sources:
  arXiv cs.CR         all years          ~20,000
  arXiv cs.LG         adversarial/back/priv/jail  ~6,500
  arXiv cs.AI         safety/jailbreak   ~2,000
  arXiv cs.SE         security/vuln/fuzz ~1,500
  IACR ePrint         2020-2025          ~6,000
  ─────────────────────────────────────────────
  Total                                  ~36,000

Usage:
    python3 fetch_large_corpus.py --output tmp_corpus_large [--resume] [--skip-iacr]
    python3 fetch_large_corpus.py --output tmp_corpus_large --resume  # restart safely

After fetching, run Corpus2Skill automatically.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ARXIV_API   = "https://export.arxiv.org/api/query"
ARXIV_NS    = {"atom": "http://www.w3.org/2005/Atom"}
BATCH_SIZE  = 100
ARXIV_RATE  = 3.0   # seconds between arXiv batch requests

IACR_BASE   = "https://eprint.iacr.org"
IACR_RATE   = 1.5   # seconds between IACR paper requests

ARXIV_SOURCES = [
    # ── cs.CR: core security/crypto, all years ───────────────────────────────
    {"label": "arXiv cs.CR (all years)",       "query": "cat:cs.CR",                          "target": 20000},
    # ── cs.LG: ML-security papers ────────────────────────────────────────────
    {"label": "arXiv cs.LG adversarial",       "query": "cat:cs.LG AND ti:adversarial",        "target": 3000},
    {"label": "arXiv cs.LG backdoor",          "query": "cat:cs.LG AND ti:backdoor",           "target": 1500},
    {"label": "arXiv cs.LG privacy",           "query": "cat:cs.LG AND ti:privacy",            "target": 1500},
    {"label": "arXiv cs.LG jailbreak",         "query": "cat:cs.LG AND ti:jailbreak",          "target":  500},
    {"label": "arXiv cs.LG membership",        "query": "cat:cs.LG AND ti:membership",         "target":  500},
    # ── cs.AI: safety / alignment / red-team ─────────────────────────────────
    {"label": "arXiv cs.AI safety",            "query": "cat:cs.AI AND ti:safety",             "target": 1200},
    {"label": "arXiv cs.AI jailbreak",         "query": "cat:cs.AI AND ti:jailbreak",          "target":  600},
    {"label": "arXiv cs.AI alignment",         "query": "cat:cs.AI AND ti:alignment",          "target":  500},
    # ── cs.SE: security engineering ──────────────────────────────────────────
    {"label": "arXiv cs.SE security",          "query": "cat:cs.SE AND ti:security",           "target":  800},
    {"label": "arXiv cs.SE vulnerability",     "query": "cat:cs.SE AND ti:vulnerability",      "target":  500},
    {"label": "arXiv cs.SE fuzzing",           "query": "cat:cs.SE AND ti:fuzz",               "target":  200},
]

IACR_YEARS        = [2025, 2024, 2023, 2022, 2021, 2020]
IACR_TARGET_TOTAL = 6000   # max IACR papers to fetch across all years

CORPUS2SKILL_NAME  = "security_large"
CORPUS2SKILL_ARGS  = ["--max-depth", "3", "--min-cluster-size", "20",
                      "--max-clusters", "8", "--overwrite"]


# ─── arXiv ──────────────────────────────────────────────────────────────────

def arxiv_batch(query: str, start: int, max_results: int) -> list[dict]:
    params = urlencode({
        "search_query": query,
        "start":        start,
        "max_results":  max_results,
        "sortBy":       "submittedDate",
        "sortOrder":    "descending",
    })
    try:
        with urlopen(f"{ARXIV_API}?{params}", timeout=40) as r:
            data = r.read()
    except (URLError, TimeoutError) as e:
        print(f"  [WARN] arXiv request failed: {e}", flush=True)
        return []

    root = ET.fromstring(data)
    return [p for e in root.findall("atom:entry", ARXIV_NS) if (p := _parse_arxiv(e))]


def _parse_arxiv(entry) -> dict | None:
    def t(tag):
        el = entry.find(tag, ARXIV_NS)
        return el.text.strip() if el is not None and el.text else ""

    raw_id   = t("atom:id")
    arxiv_id = raw_id.split("/abs/")[-1].replace("v1", "").strip("/")
    if not arxiv_id:
        return None

    title    = t("atom:title").replace("\n", " ").strip()
    abstract = t("atom:summary").replace("\n", " ").strip()
    pub      = t("atom:published")[:10]
    authors  = [a.find("atom:name", ARXIV_NS).text.strip()
                for a in entry.findall("atom:author", ARXIV_NS)
                if a.find("atom:name", ARXIV_NS) is not None]
    cats     = [c.get("term", "") for c in entry.findall("atom:category", ARXIV_NS)]

    safe_id = arxiv_id.replace("/", "_")
    return {
        "doc_id":   f"arxiv_{safe_id}",
        "title":    title,
        "authors":  authors,
        "published": pub,
        "abstract": abstract,
        "url":      f"https://arxiv.org/abs/{arxiv_id}",
        "meta":     f"arXiv:{arxiv_id}  cats:{','.join(cats[:3])}",
    }


# ─── IACR ePrint ────────────────────────────────────────────────────────────

def iacr_year_ids(year: int) -> list[str]:
    """Get paper IDs for a year from listing page; try to find max number."""
    url = f"{IACR_BASE}/{year}/"
    try:
        req = Request(url, headers={"User-Agent": "Python/security-corpus-builder"})
        with urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", errors="replace")
    except URLError as e:
        print(f"  [WARN] IACR {year} listing: {e}", flush=True)
        return []

    # Find all paper numbers mentioned in the page (any format)
    nums = re.findall(rf"\b{year}/(\d{{1,4}})\b", html)
    # Deduplicate and sort
    seen: set[str] = set()
    unique: list[str] = []
    for n in nums:
        key = f"{year}/{int(n):04d}"
        if key not in seen:
            seen.add(key)
            unique.append(f"{year}/{int(n)}")

    # If we found very few, try to infer max and fill range
    if unique:
        max_num = max(int(x.split("/")[1]) for x in unique)
        if len(unique) < max_num * 0.5:
            # Sparse listing — generate full range
            unique = [f"{year}/{i}" for i in range(1, max_num + 50)]

    return unique


def iacr_paper(paper_id: str) -> dict | None:
    """Fetch one IACR paper. Returns None on 404 or missing abstract."""
    url = f"{IACR_BASE}/{paper_id}"
    try:
        req = Request(url, headers={"User-Agent": "Python/security-corpus-builder"})
        with urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        if e.code == 404:
            return None
        print(f"  [WARN] IACR {paper_id}: HTTP {e.code}", flush=True)
        return None
    except URLError as e:
        print(f"  [WARN] IACR {paper_id}: {e}", flush=True)
        return None

    # Title from <title>
    title = ""
    m = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
    if m:
        raw = m.group(1).strip()
        raw = re.sub(r"\s*[-|]\s*Cryptology ePrint Archive.*$", "", raw, flags=re.IGNORECASE)
        title = raw.strip()

    # Abstract: <h5>Abstract</h5> <p ...>TEXT</p>
    abstract = ""
    m = re.search(r"<h5[^>]*>Abstract</h5>\s*<p[^>]*>(.*?)</p>", html, re.DOTALL | re.IGNORECASE)
    if m:
        raw = re.sub(r"<[^>]+>", " ", m.group(1)).strip()
        raw = re.sub(r"\s+", " ", raw)
        abstract = (raw.replace("&#39;", "'").replace("&quot;", '"')
                       .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))

    if not title or not abstract or len(abstract) < 50:
        return None

    authors = re.findall(r'class="authorName"[^>]*>([^<]+)', html)
    authors = [a.strip() for a in authors if a.strip()]

    year_str, num_str = paper_id.split("/")
    return {
        "doc_id":   f"iacr_{year_str}_{int(num_str):04d}",
        "title":    title,
        "authors":  authors,
        "published": f"{year_str}-01-01",
        "abstract": abstract,
        "url":      url,
        "meta":     f"IACR ePrint {paper_id}",
    }


# ─── Shared helpers ──────────────────────────────────────────────────────────

def to_md(doc: dict) -> str:
    au = ", ".join(doc["authors"][:6])
    if len(doc["authors"]) > 6:
        au += " et al."
    return (
        f"# {doc['title']}\n\n"
        f"**Authors:** {au}\n"
        f"**Date:** {doc['published']}\n"
        f"**{doc['meta']}**\n"
        f"**URL:** {doc['url']}\n\n"
        f"## Abstract\n\n{doc['abstract']}\n"
    )


def safe_fname(doc_id: str, title: str) -> str:
    s = re.sub(r"[^\w\s-]", "", title)
    s = re.sub(r"\s+", "_", s.strip())[:50].strip("_") or "doc"
    return f"{doc_id}_{s}.md"


def is_saved(doc_id: str, out_dir: Path) -> bool:
    return any(True for _ in out_dir.glob(f"{doc_id}_*.md"))


def save_progress(out_dir: Path, stats: dict) -> None:
    (out_dir / "_progress.json").write_text(
        json.dumps(stats, indent=2), encoding="utf-8"
    )


# ─── Main ────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Large-scale security corpus fetcher (~36k docs) + Corpus2Skill"
    )
    p.add_argument("--output", default="tmp_corpus_large", metavar="DIR")
    p.add_argument("--resume",       action="store_true", help="Skip already saved files")
    p.add_argument("--skip-iacr",    action="store_true", help="Skip IACR ePrint source")
    p.add_argument("--skip-corpus2skill", action="store_true",
                   help="Do not run Corpus2Skill after fetching")
    return p


def main() -> int:
    args = build_parser().parse_args()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    t_start = time.monotonic()
    stats = {"saved": 0, "sources": {}}
    total_saved = 0

    print(f"[large-fetch] Output : {out_dir.resolve()}", flush=True)
    print(f"[large-fetch] Resume : {args.resume}", flush=True)
    print(f"[large-fetch] Targets: arXiv ~{sum(s['target'] for s in ARXIV_SOURCES):,}"
          f" | IACR ~{IACR_TARGET_TOTAL:,}", flush=True)

    # ── arXiv sources ────────────────────────────────────────────────────────
    for src in ARXIV_SOURCES:
        label, query, target = src["label"], src["query"], src["target"]
        print(f"\n[large-fetch] === {label} (target={target:,}) ===", flush=True)
        src_saved = 0
        start     = 0

        while src_saved < target:
            batch = min(BATCH_SIZE, target - src_saved + 20)
            papers = arxiv_batch(query, start, batch)
            if not papers:
                print(f"  [done] No more results at start={start}", flush=True)
                break

            for p in papers:
                if src_saved >= target:
                    break
                if args.resume and is_saved(p["doc_id"], out_dir):
                    continue
                (out_dir / safe_fname(p["doc_id"], p["title"])).write_text(
                    to_md(p), encoding="utf-8"
                )
                src_saved  += 1
                total_saved += 1

            start += len(papers)
            if src_saved % 500 == 0 and src_saved > 0:
                elapsed = time.monotonic() - t_start
                print(f"  [{label}] {src_saved}/{target} | total={total_saved:,} | {elapsed/60:.1f}min", flush=True)

            if src_saved < target and len(papers) >= batch - 5:
                time.sleep(ARXIV_RATE)

        stats["sources"][label] = src_saved
        print(f"  [{label}] done: {src_saved}", flush=True)

    save_progress(out_dir, {**stats, "saved": total_saved, "phase": "arxiv_done"})

    # ── IACR ePrint ──────────────────────────────────────────────────────────
    if not args.skip_iacr:
        print(f"\n[large-fetch] === IACR ePrint 2020-2025 (target={IACR_TARGET_TOTAL:,}) ===", flush=True)
        iacr_saved  = 0
        iacr_tried  = 0
        iacr_404    = 0

        for year in IACR_YEARS:
            if iacr_saved >= IACR_TARGET_TOTAL:
                break
            print(f"  [IACR] Fetching {year} listing ...", flush=True)
            ids = iacr_year_ids(year)
            print(f"  [IACR] {year}: {len(ids)} candidate IDs", flush=True)
            time.sleep(IACR_RATE)

            for pid in ids:
                if iacr_saved >= IACR_TARGET_TOTAL:
                    break

                year_str, num_str = pid.split("/")
                doc_id = f"iacr_{year_str}_{int(num_str):04d}"
                if args.resume and is_saved(doc_id, out_dir):
                    continue

                time.sleep(IACR_RATE)
                iacr_tried += 1
                paper = iacr_paper(pid)
                if paper is None:
                    iacr_404 += 1
                    continue

                (out_dir / safe_fname(paper["doc_id"], paper["title"])).write_text(
                    to_md(paper), encoding="utf-8"
                )
                iacr_saved  += 1
                total_saved += 1

                if iacr_saved % 100 == 0:
                    elapsed = time.monotonic() - t_start
                    print(f"  [IACR] {iacr_saved} saved | tried={iacr_tried} | 404={iacr_404} | total={total_saved:,} | {elapsed/60:.1f}min", flush=True)

        stats["sources"]["IACR ePrint"] = iacr_saved
        print(f"  [IACR] done: {iacr_saved} saved, {iacr_404} 404s", flush=True)

    stats["saved"] = total_saved
    save_progress(out_dir, {**stats, "phase": "fetch_done"})

    elapsed = time.monotonic() - t_start
    total_files = len(list(out_dir.glob("*.md")))
    print(f"\n{'='*60}", flush=True)
    print(f"Fetch complete: {total_saved:,} new  |  {total_files:,} total files", flush=True)
    print(f"Elapsed: {elapsed/60:.1f} min", flush=True)
    print(f"Output : {out_dir.resolve()}", flush=True)

    # ── Corpus2Skill ─────────────────────────────────────────────────────────
    if not args.skip_corpus2skill:
        print(f"\n[large-fetch] Starting Corpus2Skill on {total_files:,} documents ...", flush=True)
        raptor_root = Path(__file__).parent
        cmd = [
            sys.executable, str(raptor_root / "raptor_corpus2skill.py"),
            "--source", str(out_dir),
            "--name",   CORPUS2SKILL_NAME,
            *CORPUS2SKILL_ARGS,
        ]
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "RAPTOR_DIR": str(raptor_root)}
        result = subprocess.run(cmd, env=env)
        return result.returncode

    print(f"\nTo build the skill hierarchy, run:", flush=True)
    print(f"  PYTHONIOENCODING=utf-8 python3 raptor_corpus2skill.py \\", flush=True)
    print(f"    --source {out_dir} --name {CORPUS2SKILL_NAME} {' '.join(CORPUS2SKILL_ARGS)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

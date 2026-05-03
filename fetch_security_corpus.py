#!/usr/bin/env python3
"""Fetch additional security research from multiple public sources.

Sources:
  1. arXiv cs.LG  - ML security (adversarial, backdoor, poisoning, jailbreak)
  2. arXiv cs.CR  - Cryptography & security 2020-2022 (complement existing 2023+)
  3. arXiv cs.AI  - AI safety/alignment/red-team papers
  4. IACR ePrint  - Cryptography research (2023-2024)

Usage:
    python3 fetch_security_corpus.py --output tmp_security_extra --count 500
    python3 fetch_security_corpus.py --output tmp_security_extra --count 500 --resume
"""
import argparse
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError

ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}
BATCH_SIZE = 100
ARXIV_RATE = 3.0

IACR_BASE = "https://eprint.iacr.org"
IACR_RATE = 2.0

ARXIV_SOURCES = [
    {
        "label": "arXiv cs.LG (ML security)",
        "query": "cat:cs.LG AND ti:adversarial",
        "target": 80,
    },
    {
        "label": "arXiv cs.LG (backdoor/poisoning)",
        "query": "cat:cs.LG AND ti:backdoor",
        "target": 70,
    },
    {
        "label": "arXiv cs.CR 2020-2022",
        "query": "cat:cs.CR AND submittedDate:[202001010000 TO 202212312359]",
        "target": 150,
    },
    {
        "label": "arXiv cs.AI (safety/jailbreak)",
        "query": "cat:cs.AI AND ti:safety",
        "target": 60,
    },
    {
        "label": "arXiv cs.AI (jailbreak)",
        "query": "cat:cs.AI AND ti:jailbreak",
        "target": 40,
    },
]

IACR_YEARS = [2024, 2023]
IACR_TARGET = 100


# ─── arXiv helpers ──────────────────────────────────────────────────────────

def arxiv_fetch_batch(query: str, start: int, max_results: int) -> list[dict]:
    params = urlencode({
        "search_query": query,
        "start": start,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    try:
        with urlopen(f"{ARXIV_API}?{params}", timeout=30) as resp:
            data = resp.read()
    except URLError as e:
        print(f"  [WARN] arXiv error: {e}", flush=True)
        return []

    root = ET.fromstring(data)
    results = []
    for entry in root.findall("atom:entry", ARXIV_NS):
        p = _parse_arxiv_entry(entry)
        if p:
            results.append(p)
    return results


def _parse_arxiv_entry(entry) -> dict | None:
    def t(tag):
        el = entry.find(tag, ARXIV_NS)
        return el.text.strip() if el is not None and el.text else ""

    raw_id = t("atom:id")
    arxiv_id = raw_id.split("/abs/")[-1].replace("v1", "").strip("/")
    if not arxiv_id:
        return None

    title = t("atom:title").replace("\n", " ").strip()
    abstract = t("atom:summary").replace("\n", " ").strip()
    published = t("atom:published")[:10]
    authors = [
        a.find("atom:name", ARXIV_NS).text.strip()
        for a in entry.findall("atom:author", ARXIV_NS)
        if a.find("atom:name", ARXIV_NS) is not None
    ]
    cats = [c.get("term", "") for c in entry.findall("atom:category", ARXIV_NS)]

    safe_id = arxiv_id.replace("/", "_")
    return {
        "doc_id": f"arxiv_{safe_id}",
        "title": title,
        "authors": authors,
        "published": published,
        "abstract": abstract,
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "meta": f"arXiv:{arxiv_id}  Categories: {', '.join(cats[:4])}",
    }


# ─── IACR helpers ───────────────────────────────────────────────────────────

def iacr_fetch_year_ids(year: int) -> list[str]:
    """Return list of paper IDs (e.g. '2024/001') from year listing."""
    url = f"{IACR_BASE}/{year}/"
    try:
        req = Request(url, headers={"User-Agent": "Python/security-corpus-builder"})
        with urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except URLError as e:
        print(f"  [WARN] IACR {year} listing failed: {e}", flush=True)
        return []

    # Links like href="/2024/001" or href="/2024/1234"
    ids = re.findall(r'href="/{year}/(\d+)"'.replace("{year}", str(year)), html)
    # Also match absolute paths
    ids += re.findall(r'href="https://eprint\.iacr\.org/{}/(\d+)"'.format(year), html)
    # Deduplicate preserving order
    seen = set()
    unique = []
    for i in ids:
        key = f"{year}/{i.zfill(4)}"
        if key not in seen:
            seen.add(key)
            unique.append(f"{year}/{i}")
    return unique


def iacr_fetch_paper(paper_id: str) -> dict | None:
    """Fetch title, authors, abstract for one IACR paper."""
    url = f"{IACR_BASE}/{paper_id}"
    try:
        req = Request(url, headers={"User-Agent": "Python/security-corpus-builder"})
        with urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except URLError as e:
        print(f"  [WARN] IACR {paper_id} failed: {e}", flush=True)
        return None

    # Title: <title>Paper Title - Cryptology ePrint Archive</title>
    title = ""
    m = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
    if m:
        raw = m.group(1).strip()
        raw = re.sub(r"\s*[-|]\s*Cryptology ePrint Archive.*$", "", raw, flags=re.IGNORECASE)
        title = raw.strip()

    # Abstract: <h5>Abstract</h5>\n<p style="white-space: pre-wrap;">TEXT</p>
    abstract = ""
    m = re.search(
        r"<h5[^>]*>Abstract</h5>\s*<p[^>]*>(.*?)</p>",
        html, re.DOTALL | re.IGNORECASE,
    )
    if m:
        raw = m.group(1)
        abstract = re.sub(r"<[^>]+>", " ", raw).strip()
        abstract = re.sub(r"\s+", " ", abstract)
        # Unescape common HTML entities
        abstract = abstract.replace("&#39;", "'").replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")

    if not title or not abstract or len(abstract) < 50:
        return None

    # Authors: <span class="authorName">Name</span>
    authors = re.findall(r'class="authorName"[^>]*>([^<]+)', html)
    authors = [a.strip() for a in authors if a.strip()]

    year_str = paper_id.split("/")[0]
    num_str = paper_id.split("/")[1].zfill(4)
    return {
        "doc_id": f"iacr_{year_str}_{num_str}",
        "title": title,
        "authors": authors,
        "published": f"{year_str}-01-01",
        "abstract": abstract,
        "url": url,
        "meta": f"IACR ePrint {paper_id}",
    }


# ─── Shared writers ──────────────────────────────────────────────────────────

def to_markdown(doc: dict) -> str:
    authors_str = ", ".join(doc["authors"][:6])
    if len(doc["authors"]) > 6:
        authors_str += " et al."
    return (
        f"# {doc['title']}\n\n"
        f"**Authors:** {authors_str}\n"
        f"**Date:** {doc['published']}\n"
        f"**{doc['meta']}**\n"
        f"**URL:** {doc['url']}\n\n"
        f"## Abstract\n\n{doc['abstract']}\n"
    )


def safe_filename(doc_id: str, title: str) -> str:
    safe = re.sub(r"[^\w\s-]", "", title)
    safe = re.sub(r"\s+", "_", safe.strip())[:50].strip("_")
    return f"{doc_id}_{safe}.md"


def already_saved(doc_id: str, out_dir: Path) -> bool:
    return any(True for _ in out_dir.glob(f"{doc_id}_*.md"))


# ─── Main ────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fetch security corpus from multiple sources (arXiv + IACR ePrint)"
    )
    p.add_argument("--output", default="tmp_security_extra", metavar="DIR")
    p.add_argument("--count", type=int, default=500)
    p.add_argument("--resume", action="store_true", help="Skip already saved papers")
    p.add_argument("--skip-iacr", action="store_true", help="Skip IACR ePrint source")
    return p


def main() -> int:
    args = build_parser().parse_args()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    target = args.count
    saved = 0

    print(f"[fetch] Target: {target} documents", flush=True)
    print(f"[fetch] Output: {out_dir.resolve()}", flush=True)

    # ── arXiv sources ────────────────────────────────────────────────────────
    for src in ARXIV_SOURCES:
        if saved >= target:
            break
        src_target = min(src["target"], target - saved)
        print(f"\n[fetch] === {src['label']} (target={src_target}) ===", flush=True)

        start = 0
        src_saved = 0

        while src_saved < src_target:
            batch = min(BATCH_SIZE, src_target - src_saved + 20)
            print(f"[fetch]   batch start={start} size={batch} ...", flush=True)
            papers = arxiv_fetch_batch(src["query"], start, batch)

            if not papers:
                print("[fetch]   No more results", flush=True)
                break

            for paper in papers:
                if src_saved >= src_target or saved >= target:
                    break
                if args.resume and already_saved(paper["doc_id"], out_dir):
                    continue
                fname = safe_filename(paper["doc_id"], paper["title"])
                (out_dir / fname).write_text(to_markdown(paper), encoding="utf-8")
                src_saved += 1
                saved += 1
                if saved % 50 == 0:
                    print(f"[fetch]   Total: {saved}/{target}", flush=True)

            start += len(papers)
            if src_saved < src_target and len(papers) >= batch - 5:
                print(f"[fetch]   Rate limit {ARXIV_RATE}s ...", flush=True)
                time.sleep(ARXIV_RATE)

        print(f"[fetch]   {src['label']}: saved {src_saved}", flush=True)

    # ── IACR ePrint ──────────────────────────────────────────────────────────
    if not args.skip_iacr and saved < target:
        iacr_target = min(IACR_TARGET, target - saved)
        print(f"\n[fetch] === IACR ePrint (target={iacr_target}) ===", flush=True)
        iacr_saved = 0

        for year in IACR_YEARS:
            if iacr_saved >= iacr_target:
                break
            print(f"[fetch]   Fetching {year} paper list ...", flush=True)
            ids = iacr_fetch_year_ids(year)
            print(f"[fetch]   Found {len(ids)} paper IDs in {year}", flush=True)
            if not ids:
                continue

            time.sleep(IACR_RATE)
            for pid in ids:
                if iacr_saved >= iacr_target or saved >= target:
                    break
                doc_id = f"iacr_{pid.replace('/', '_')}"
                if args.resume and already_saved(doc_id, out_dir):
                    continue
                time.sleep(IACR_RATE)
                paper = iacr_fetch_paper(pid)
                if not paper:
                    continue
                fname = safe_filename(paper["doc_id"], paper["title"])
                (out_dir / fname).write_text(to_markdown(paper), encoding="utf-8")
                iacr_saved += 1
                saved += 1
                if saved % 25 == 0:
                    print(f"[fetch]   Total: {saved}/{target}", flush=True)

        print(f"[fetch]   IACR ePrint: saved {iacr_saved}", flush=True)

    total_in_dir = len(list(out_dir.glob("*.md")))
    print(f"\n[fetch] Done: {saved} new, {total_in_dir} total in {out_dir.resolve()}", flush=True)
    print(f"[fetch] Merge all into Corpus2Skill with:", flush=True)
    print(f"  PYTHONIOENCODING=utf-8 python3 raptor_corpus2skill.py \\", flush=True)
    print(f"    --source {out_dir} --name security_extended --overwrite", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Fetch security papers from arXiv API (cs.CR category) and save as markdown.

Usage:
    python3 fetch_arxiv_papers.py --output tmp_papers --count 500 --since 2023-01-01
    python3 fetch_arxiv_papers.py --output tmp_papers --count 500 --since 2023-01-01 --resume
"""
import argparse
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import URLError

ARXIV_API = "http://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
BATCH_SIZE = 100   # arXiv API max recommended per request
RATE_LIMIT  = 3.0  # seconds between requests (arXiv asks for polite crawling)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fetch arXiv cs.CR papers and save as markdown files"
    )
    p.add_argument("--output", default="tmp_papers", metavar="DIR",
                   help="Output directory for markdown files (default: tmp_papers)")
    p.add_argument("--count", type=int, default=500, metavar="N",
                   help="Target number of papers to fetch (default: 500)")
    p.add_argument("--since", default="2023-01-01", metavar="YYYY-MM-DD",
                   help="Fetch papers submitted from this date (default: 2023-01-01)")
    p.add_argument("--category", default="cs.CR", metavar="CAT",
                   help="arXiv category (default: cs.CR)")
    p.add_argument("--resume", action="store_true",
                   help="Skip papers already saved in output dir")
    return p


def fetch_batch(category: str, since: str, start: int, max_results: int) -> list[dict]:
    """Fetch one batch of papers from arXiv API."""
    # date_from format: YYYYMMDD0000 to YYYYMMDD2359
    date_from = since.replace("-", "") + "0000"
    query = f"cat:{category} AND submittedDate:[{date_from} TO 99991231235900]"

    params = urlencode({
        "search_query": query,
        "start": start,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    url = f"{ARXIV_API}?{params}"

    try:
        with urlopen(url, timeout=30) as resp:
            xml_data = resp.read()
    except URLError as e:
        print(f"  [WARN] Request failed: {e}", flush=True)
        return []

    root = ET.fromstring(xml_data)
    papers = []

    for entry in root.findall("atom:entry", NS):
        paper = _parse_entry(entry)
        if paper:
            papers.append(paper)

    return papers


def _parse_entry(entry) -> dict | None:
    def text(tag):
        el = entry.find(tag, NS)
        return el.text.strip() if el is not None and el.text else ""

    arxiv_id_raw = text("atom:id")
    # Extract ID like "2506.12345" from URL
    arxiv_id = arxiv_id_raw.split("/abs/")[-1].replace("v1", "").strip("/")
    if not arxiv_id:
        return None

    title   = text("atom:title").replace("\n", " ").strip()
    summary = text("atom:summary").replace("\n", " ").strip()
    published = text("atom:published")[:10]

    authors = [
        a.find("atom:name", NS).text.strip()
        for a in entry.findall("atom:author", NS)
        if a.find("atom:name", NS) is not None
    ]

    categories = [
        c.get("term", "")
        for c in entry.findall("atom:category", NS)
    ]

    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "authors": authors,
        "published": published,
        "abstract": summary,
        "categories": categories,
        "url": f"https://arxiv.org/abs/{arxiv_id}",
    }


def paper_to_markdown(paper: dict) -> str:
    authors_str = ", ".join(paper["authors"][:6])
    if len(paper["authors"]) > 6:
        authors_str += " et al."
    cats = ", ".join(paper["categories"][:4])

    return f"""# {paper["title"]}

**Authors:** {authors_str}
**Date:** {paper["published"]}
**arXiv:** {paper["arxiv_id"]}
**URL:** {paper["url"]}
**Categories:** {cats}

## Abstract

{paper["abstract"]}
"""


def safe_filename(arxiv_id: str, title: str) -> str:
    import re
    safe = re.sub(r"[^\w\s-]", "", title)
    safe = re.sub(r"\s+", "_", safe.strip())[:60].strip("_")
    arxiv_clean = arxiv_id.replace("/", "_")
    return f"{arxiv_clean}_{safe}.md"


def main() -> int:
    args = build_parser().parse_args()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Collect already-saved IDs for resume
    existing_ids: set[str] = set()
    if args.resume:
        for f in out_dir.glob("*.md"):
            # First part of filename is arxiv_id (dots replaced with underscore)
            existing_ids.add(f.stem.split("_")[0] + "." + f.stem.split("_")[1]
                              if "_" in f.stem else "")
        print(f"[fetch] Resume mode: {len(existing_ids)} papers already saved", flush=True)

    saved = 0
    skipped = 0
    start = 0
    target = args.count

    print(f"[fetch] Target: {target} papers from {args.category} since {args.since}", flush=True)
    print(f"[fetch] Output: {out_dir.resolve()}", flush=True)
    print(flush=True)

    while saved < target:
        batch_size = min(BATCH_SIZE, target - saved + 20)  # fetch a bit extra
        print(f"[fetch] Fetching batch start={start} size={batch_size} ...", flush=True)

        papers = fetch_batch(args.category, args.since, start, batch_size)
        if not papers:
            print("[fetch] No more papers returned — done.", flush=True)
            break

        for paper in papers:
            if saved >= target:
                break

            arxiv_id = paper["arxiv_id"]

            # Skip if resume and already exists
            if args.resume and any(arxiv_id.replace(".", "_") in f.stem
                                   for f in out_dir.glob("*.md")):
                skipped += 1
                continue

            filename = safe_filename(arxiv_id, paper["title"])
            filepath = out_dir / filename
            filepath.write_text(paper_to_markdown(paper), encoding="utf-8")
            saved += 1

            if saved % 50 == 0:
                print(f"[fetch]   Saved {saved}/{target} papers ...", flush=True)

        start += len(papers)

        # Polite rate limiting between batches
        if saved < target and len(papers) == batch_size:
            print(f"[fetch] Waiting {RATE_LIMIT}s (arXiv rate limit) ...", flush=True)
            time.sleep(RATE_LIMIT)

    print(flush=True)
    print(f"[fetch] Done: {saved} new, {skipped} skipped, total in dir: "
          f"{len(list(out_dir.glob('*.md')))}", flush=True)
    print(f"[fetch] Run Corpus2Skill with:", flush=True)
    print(f"  PYTHONIOENCODING=utf-8 python3 raptor_corpus2skill.py "
          f"--source {out_dir} --name arxiv_cr_2023plus --overwrite", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

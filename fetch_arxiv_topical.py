#!/usr/bin/env python3
"""Fetch arXiv papers by free-form query and save as markdown.

Sibling of fetch_arxiv_papers.py — that one is locked to cs.CR. This one
accepts arbitrary arXiv search_query expressions (e.g. "all:agent AND
all:planning") so we can populate topic-scoped RAD domain corpora.

Usage:
    python fetch_arxiv_topical.py --query "all:llm AND all:agent" \
        --output .claude/skills/corpus/agents_corpus/papers --count 200

    python fetch_arxiv_topical.py --query-file domain_queries.txt \
        --output .claude/skills/corpus/llm_corpus/papers --per-query 150
"""
import argparse
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import URLError

ARXIV_API = "https://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
BATCH_SIZE = 100
RATE_LIMIT = 3.0


def build_parser():
    p = argparse.ArgumentParser(description="Fetch arXiv papers by free-form query")
    p.add_argument("--query", help="Single arXiv search_query expression")
    p.add_argument("--query-file", help="File with one query per line")
    p.add_argument("--output", required=True, metavar="DIR",
                   help="Output directory for markdown files")
    p.add_argument("--count", type=int, default=200,
                   help="Total papers (single query mode, default 200)")
    p.add_argument("--per-query", type=int, default=150,
                   help="Papers per query (query-file mode, default 150)")
    p.add_argument("--since", default="2022-01-01",
                   help="Earliest submittedDate filter (default 2022-01-01)")
    return p


def fetch_batch(query: str, since: str, start: int, max_results: int):
    """Fetch one batch with exponential-backoff retry on 429 / transient errors.

    Returns ([], rate_limited=False) on a true empty result, ([], True) on
    repeated 429s so the caller can distinguish "no more papers" from "throttled".
    """
    date_from = since.replace("-", "") + "0000"
    full_query = f"({query}) AND submittedDate:[{date_from} TO 99991231235900]"
    params = urlencode({
        "search_query": full_query,
        "start": start,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    url = f"{ARXIV_API}?{params}"

    delay = 30.0
    for attempt in range(5):
        try:
            with urlopen(url, timeout=60) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
            return [_parse_entry(e) for e in root.findall("atom:entry", NS)
                    if _parse_entry(e)], False
        except URLError as e:
            msg = str(e)
            if "429" in msg or "Too Many" in msg or "timed out" in msg:
                print(f"  [BACKOFF] 429/timeout attempt {attempt+1}/5 - sleep {delay}s", flush=True)
                time.sleep(delay)
                delay = min(delay * 2, 300)
                continue
            print(f"  [WARN] {e}", flush=True)
            return [], False
    print(f"  [GAVE UP] still 429 after retries", flush=True)
    return [], True


def _parse_entry(entry):
    def text(tag):
        el = entry.find(tag, NS)
        return el.text.strip() if el is not None and el.text else ""
    arxiv_id_raw = text("atom:id")
    arxiv_id = arxiv_id_raw.split("/abs/")[-1].split("v")[0].strip("/")
    if not arxiv_id:
        return None
    return {
        "arxiv_id": arxiv_id,
        "title": text("atom:title").replace("\n", " ").strip(),
        "authors": [a.find("atom:name", NS).text.strip()
                    for a in entry.findall("atom:author", NS)
                    if a.find("atom:name", NS) is not None],
        "published": text("atom:published")[:10],
        "abstract": text("atom:summary").replace("\n", " ").strip(),
        "categories": [c.get("term", "") for c in entry.findall("atom:category", NS)],
        "url": f"https://arxiv.org/abs/{arxiv_id}",
    }


def to_markdown(paper, source_query: str = ""):
    authors = ", ".join(paper["authors"][:6])
    if len(paper["authors"]) > 6:
        authors += " et al."
    cats = ", ".join(paper["categories"][:4])
    source_query_line = ""
    if source_query:
        source_query_line = f"<!-- source-query: {source_query} -->\n"
    return (f"# {paper['title']}\n\n"
            f"**Authors:** {authors}\n"
            f"**Date:** {paper['published']}\n"
            f"**arXiv:** {paper['arxiv_id']}\n"
            f"**URL:** {paper['url']}\n"
            f"{source_query_line}"
            f"**Categories:** {cats}\n\n## Abstract\n\n{paper['abstract']}\n")


def safe_filename(arxiv_id, title):
    safe = re.sub(r"[^\w\s-]", "", title)
    safe = re.sub(r"\s+", "_", safe.strip())[:60].strip("_")
    return f"{arxiv_id.replace('/', '_').replace('.', '_')}_{safe}.md"


def run_query(query: str, target: int, since: str, out_dir: Path):
    saved = 0
    skipped = 0
    start = 0
    print(f"[fetch] Query: {query!r} target={target}", flush=True)
    while saved < target:
        batch_size = min(BATCH_SIZE, target - saved + 20)
        papers, throttled = fetch_batch(query, since, start, batch_size)
        if throttled:
            print("[fetch]   Aborting query: still throttled after retries.", flush=True)
            break
        if not papers:
            print("[fetch]   No more results.", flush=True)
            break
        for p in papers:
            if saved >= target:
                break
            fp = out_dir / safe_filename(p["arxiv_id"], p["title"])
            if fp.exists():
                skipped += 1
                continue
            fp.write_text(to_markdown(p, source_query=query), encoding="utf-8")
            saved += 1
        start += len(papers)
        if saved < target and len(papers) == batch_size:
            time.sleep(RATE_LIMIT)
    print(f"[fetch]   Saved {saved}, skipped {skipped} (existing).", flush=True)
    return saved


def main():
    args = build_parser().parse_args()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    queries = []
    if args.query:
        queries.append((args.query, args.count))
    if args.query_file:
        for line in Path(args.query_file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                queries.append((line, args.per_query))
    if not queries:
        print("[fetch] No queries specified (--query or --query-file required)", file=sys.stderr)
        return 2

    total = 0
    for q, n in queries:
        total += run_query(q, n, args.since, out_dir)
        time.sleep(RATE_LIMIT)
    print(f"[fetch] Total saved: {total} new papers in {out_dir}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Google Project Zero blog fetcher.

Fetches the Atom/RSS feed from https://googleprojectzero.blogspot.com/feeds/posts/default
and converts each post to a Markdown file for corpus2skill ingestion.

Rate limit: 0.5 seconds.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from packages.hacker_corpus.base import CorpusFetcher, FetchResult

_FEED_BASE = (
    "https://googleprojectzero.blogspot.com/feeds/posts/default"
)
_TIMEOUT = 20
_PAGE_SIZE = 25  # posts per request


# Atom namespace
_ATOM_NS = "http://www.w3.org/2005/Atom"


def _html_to_text(html: str) -> str:
    """Very basic HTML → plain text (tags stripped, entities decoded)."""
    text = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", html, flags=re.S)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<p[^>]*>", "\n\n", text, flags=re.I)
    text = re.sub(r"</p>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
    )
    return text.strip()


def _safe_filename(title: str) -> str:
    """Convert a blog post title to a safe filename."""
    name = re.sub(r"[^A-Za-z0-9_\- ]", "", title)
    name = name.strip().replace(" ", "_")
    return name[:80] or "post"


class ProjectZeroFetcher(CorpusFetcher):
    name = "project_zero"
    rate_limit = 0.5

    def __init__(self, output_dir: Path, force: bool = False) -> None:
        super().__init__(output_dir / "project_zero", force=force)

    def _do_fetch(self, result: FetchResult) -> None:
        start_index = 1

        while True:
            url = f"{_FEED_BASE}?start-index={start_index}&max-results={_PAGE_SIZE}"
            try:
                resp = requests.get(url, timeout=_TIMEOUT)
                resp.raise_for_status()
            except Exception as exc:
                result.errors.append(f"Feed page start={start_index}: {exc}")
                break
            finally:
                self._sleep()

            try:
                root = ET.fromstring(resp.content)
            except ET.ParseError as exc:
                result.errors.append(f"XML parse error at start={start_index}: {exc}")
                break

            entries = root.findall(f"{{{_ATOM_NS}}}entry")
            if not entries:
                break

            for entry in entries:
                self._save_entry(entry, result)

            start_index += _PAGE_SIZE

    def _save_entry(self, entry: ET.Element, result: FetchResult) -> None:
        def txt(tag: str) -> str:
            el = entry.find(f"{{{_ATOM_NS}}}{tag}")
            if el is None:
                return ""
            return (el.text or "").strip()

        title = txt("title") or "untitled"
        published = txt("published")
        updated = txt("updated")

        # Content may be in <content> or <summary>
        content_el = entry.find(f"{{{_ATOM_NS}}}content")
        if content_el is None:
            content_el = entry.find(f"{{{_ATOM_NS}}}summary")
        raw_content = "".join(content_el.itertext()) if content_el is not None else ""

        body = _html_to_text(raw_content) if raw_content else ""

        # Get the alternate link (blog URL) for reference
        link_url = ""
        for link_el in entry.findall(f"{{{_ATOM_NS}}}link"):
            if link_el.get("rel") == "alternate":
                link_url = link_el.get("href", "")
                break

        filename = _safe_filename(title)
        # Prefix with date for ordering
        date_prefix = published[:10].replace("-", "") if published else "00000000"
        out_path = self.output_dir / f"{date_prefix}_{filename}.md"

        if self._should_skip(out_path):
            result.skipped += 1
            return

        lines = [
            f"# {title}",
            "",
            f"**Published:** {published}",
            f"**Updated:** {updated}",
        ]
        if link_url:
            lines.append(f"**Source:** {link_url}")
        lines += ["", "---", "", body]

        self._safe_write(out_path, "\n".join(lines))
        result.count += 1

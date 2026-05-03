"""
OSS-Security mailing list fetcher.

Scrapes https://www.openwall.com/lists/oss-security/ for the past 3 years
of security disclosure messages and saves them as text files.

Rate limit: 0.5 seconds between requests.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from html.parser import HTMLParser

from packages.hacker_corpus.base import CorpusFetcher, FetchResult

_BASE_URL = "https://www.openwall.com/lists/oss-security"
_TIMEOUT = 20


class _LinkParser(HTMLParser):
    """Minimal parser to extract hrefs from an HTML page."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            for attr, val in attrs:
                if attr == "href" and val:
                    self.links.append(val)


def _extract_links(html: str) -> list[str]:
    parser = _LinkParser()
    parser.feed(html)
    return parser.links


def _html_to_text(html: str) -> str:
    """Very simple HTML → plain text conversion."""
    # Remove script/style blocks
    text = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", html, flags=re.S)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common entities
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
    )
    # Collapse whitespace
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip()


class OSSSecurityFetcher(CorpusFetcher):
    name = "oss_security"
    rate_limit = 0.5

    def __init__(self, output_dir: Path, force: bool = False) -> None:
        super().__init__(output_dir / "oss_security", force=force)
        self._cutoff_year = datetime.now(tz=timezone.utc).year - 3

    def _do_fetch(self, result: FetchResult) -> None:
        # Fetch monthly archive index pages for the past 3 years
        current = datetime.now(tz=timezone.utc)
        year = self._cutoff_year
        while year <= current.year:
            month_end = 13 if year < current.year else current.month + 1
            for month in range(1, month_end):
                self._fetch_month(year, month, result)
            year += 1

    def _fetch_month(self, year: int, month: int, result: FetchResult) -> None:
        month_url = f"{_BASE_URL}/{year}/{month:02d}/"
        try:
            resp = requests.get(month_url, timeout=_TIMEOUT)
        except Exception as exc:
            result.errors.append(f"{year}/{month:02d} index: {exc}")
            return
        finally:
            self._sleep()

        if not resp.ok:
            # Month may not exist yet
            return

        # Find links to individual messages (typically numeric)
        links = _extract_links(resp.text)
        msg_nums: list[str] = []
        for lnk in links:
            # Message links like "1", "2", "../1" etc.
            m = re.match(r"^(?:\./)?(\d+)/?$", lnk.strip())
            if m:
                msg_nums.append(m.group(1))

        for num in msg_nums:
            self._fetch_message(year, month, num, result)

    def _fetch_message(
        self, year: int, month: int, num: str, result: FetchResult
    ) -> None:
        out_path = self.output_dir / f"{year}" / f"{month:02d}_{num}.txt"

        if self._should_skip(out_path):
            result.skipped += 1
            return

        msg_url = f"{_BASE_URL}/{year}/{month:02d}/{num}"
        try:
            resp = requests.get(msg_url, timeout=_TIMEOUT)
        except Exception as exc:
            result.errors.append(f"Message {year}/{month:02d}/{num}: {exc}")
            return
        finally:
            self._sleep()

        if not resp.ok:
            result.errors.append(
                f"Message {year}/{month:02d}/{num}: HTTP {resp.status_code}"
            )
            return

        text = _html_to_text(resp.text)
        if not text:
            return

        self._safe_write(out_path, text)
        result.count += 1

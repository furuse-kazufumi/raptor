"""
Phrack magazine fetcher.

Downloads articles from https://phrack.org/issues/ and saves them
as plain-text files for corpus2skill ingestion.

Rate limit: 1 second between requests (polite scraping).
"""

from __future__ import annotations

import re
from pathlib import Path

import requests

from packages.hacker_corpus.base import CorpusFetcher, FetchResult

_BASE = "https://phrack.org"
_TIMEOUT = 15
# Issues 1-70 are known to exist; article txt at /archives/issues/{N}/{A}.txt
_KNOWN_ISSUES = list(range(1, 71))


class PhrackFetcher(CorpusFetcher):
    name = "phrack"
    rate_limit = 1.0

    def __init__(self, output_dir: Path, force: bool = False) -> None:
        super().__init__(output_dir / "phrack", force=force)

    def _do_fetch(self, result: FetchResult) -> None:
        try:
            issues = self._get_issue_numbers()
        except Exception as exc:
            result.errors.append(f"Failed to fetch issue index: {exc}")
            return

        for issue_num in issues:
            self._fetch_issue(issue_num, result)

    # ------------------------------------------------------------------

    def _get_issue_numbers(self) -> list[int]:
        return _KNOWN_ISSUES

    def _fetch_issue(self, issue_num: int, result: FetchResult) -> None:
        """Fetch articles 1-25 for a given issue using the txt archive URL."""
        issue_dir = self.output_dir / f"issue_{issue_num}"
        for article_num in range(1, 26):
            self._fetch_article(issue_num, article_num, issue_dir, result)

    def _fetch_article(
        self,
        issue_num: int,
        article_num: int,
        issue_dir: Path,
        result: FetchResult,
    ) -> None:
        out_path = issue_dir / f"article_{article_num:02d}.txt"

        if self._should_skip(out_path):
            result.skipped += 1
            return

        url = f"{_BASE}/archives/issues/{issue_num}/{article_num}.txt"
        try:
            resp = requests.get(url, timeout=_TIMEOUT)
        except Exception as exc:
            result.errors.append(f"Issue {issue_num} article {article_num}: {exc}")
            return
        finally:
            self._sleep()

        if resp.status_code == 404:
            # Article does not exist; skip silently
            return
        if not resp.ok:
            result.errors.append(
                f"Issue {issue_num} article {article_num}: HTTP {resp.status_code}"
            )
            return

        text = resp.text.strip()
        if not text:
            return

        self._safe_write(out_path, text)
        result.count += 1

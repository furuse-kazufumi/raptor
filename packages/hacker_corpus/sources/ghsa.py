"""
GitHub Security Advisory (GHSA) fetcher.

Uses the GitHub GraphQL API to fetch security advisories and saves
each as a JSON file for corpus2skill ingestion.

Rate limit: 0.5 seconds between requests.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from packages.hacker_corpus.base import CorpusFetcher, FetchResult

_GRAPHQL_URL = "https://api.github.com/graphql"
_TIMEOUT = 20

_QUERY = """
query($cursor: String) {
  securityAdvisories(first: 100, after: $cursor) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      ghsaId
      summary
      description
      severity
      publishedAt
      updatedAt
      references {
        url
      }
      vulnerabilities(first: 10) {
        nodes {
          package {
            ecosystem
            name
          }
          firstPatchedVersion {
            identifier
          }
          vulnerableVersionRange
        }
      }
      cwes(first: 5) {
        nodes {
          cweId
          name
        }
      }
    }
  }
}
"""


class GHSAFetcher(CorpusFetcher):
    name = "ghsa"
    rate_limit = 0.5

    def __init__(self, output_dir: Path, force: bool = False) -> None:
        super().__init__(output_dir / "ghsa", force=force)
        self._token = os.environ.get("GITHUB_TOKEN", "")

    def _do_fetch(self, result: FetchResult) -> None:
        cursor: str | None = None
        page = 0

        while True:
            page += 1
            try:
                data, has_next, cursor = self._fetch_page(cursor)
            except Exception as exc:
                result.errors.append(f"GraphQL page {page}: {exc}")
                break

            for advisory in data:
                self._save_advisory(advisory, result)

            self._sleep()

            if not has_next:
                break

    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"bearer {self._token}"
        return headers

    def _fetch_page(
        self, cursor: str | None
    ) -> tuple[list[dict], bool, str | None]:
        variables: dict = {}
        if cursor:
            variables["cursor"] = cursor

        payload = {"query": _QUERY, "variables": variables}
        resp = requests.post(
            _GRAPHQL_URL,
            headers=self._headers(),
            json=payload,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()

        body = resp.json()
        if "errors" in body:
            raise RuntimeError(body["errors"])

        sa = body["data"]["securityAdvisories"]
        page_info = sa["pageInfo"]
        nodes = sa["nodes"]
        return nodes, page_info["hasNextPage"], page_info.get("endCursor")

    def _save_advisory(self, advisory: dict, result: FetchResult) -> None:
        ghsa_id = advisory.get("ghsaId", "UNKNOWN")
        out_path = self.output_dir / f"{ghsa_id}.json"

        if self._should_skip(out_path):
            result.skipped += 1
            return

        self._safe_write(out_path, json.dumps(advisory, ensure_ascii=False, indent=2))
        result.count += 1

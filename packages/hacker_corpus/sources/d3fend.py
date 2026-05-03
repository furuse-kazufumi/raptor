"""
D3FEND (MITRE D3FEND) fetcher.

Downloads the D3FEND full mappings JSON and converts each defensive
technique to a Markdown file for corpus2skill ingestion.

Rate limit: 0.5 seconds (single download, local parsing).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from packages.hacker_corpus.base import CorpusFetcher, FetchResult

_D3FEND_URL = (
    "https://d3fend.mitre.org/api/ontology/inference/d3fend-full-mappings.json"
)
_TIMEOUT = 60


class D3FENDFetcher(CorpusFetcher):
    name = "d3fend"
    rate_limit = 0.5

    def __init__(self, output_dir: Path, force: bool = False) -> None:
        super().__init__(output_dir / "d3fend", force=force)

    def _do_fetch(self, result: FetchResult) -> None:
        cache_path = self.output_dir / "_d3fend_mappings.json"

        if cache_path.exists() and not self.force:
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception as exc:
                result.errors.append(f"Cache read error: {exc}")
                return
        else:
            try:
                resp = requests.get(_D3FEND_URL, timeout=_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                self._safe_write(
                    cache_path,
                    json.dumps(data, ensure_ascii=False, indent=2),
                )
            except Exception as exc:
                result.errors.append(f"Failed to download D3FEND data: {exc}")
                return

        # The JSON structure varies; handle both list and dict top-levels
        techniques = self._extract_techniques(data)
        for tech in techniques:
            self._save_technique(tech, result)

    def _extract_techniques(self, data: object) -> list[dict]:
        """Extract technique dicts from the D3FEND JSON.

        Handles SPARQL {'head':..., 'results':{'bindings':[...]}} format by
        grouping bindings by defense technique name.
        """
        # SPARQL format: data['results']['bindings'] is the binding list
        bindings: list[dict] = []
        if isinstance(data, dict):
            results = data.get("results", {})
            if isinstance(results, dict):
                bindings = results.get("bindings", [])
            elif isinstance(results, list):
                bindings = results
        elif isinstance(data, list):
            bindings = data

        if not bindings:
            return []

        # Group bindings by defense technique label; each group → one file
        grouped: dict[str, dict] = {}
        for b in bindings:
            def _v(key: str) -> str:
                entry = b.get(key, {})
                return entry.get("value", "") if isinstance(entry, dict) else str(entry)

            def_tech = _v("def_tech_label") or _v("query_def_tech_label")
            if not def_tech:
                continue
            if def_tech not in grouped:
                grouped[def_tech] = {
                    "def_tech_label": def_tech,
                    "def_tactic_label": _v("def_tactic_label"),
                    "top_def_tech_label": _v("top_def_tech_label"),
                    "off_techniques": [],
                }
            off_tech = _v("off_tech_label")
            off_id = _v("off_tech_id")
            off_tactic = _v("off_tactic_label")
            if off_tech:
                grouped[def_tech]["off_techniques"].append(
                    f"{off_id} {off_tech} ({off_tactic})"
                )

        return list(grouped.values())

    def _save_technique(self, tech: dict, result: FetchResult) -> None:
        name = tech.get("def_tech_label", "unknown")
        safe_id = re.sub(r"[^A-Za-z0-9_\-]", "_", name)[:80] or "unknown"
        out_path = self.output_dir / f"{safe_id}.md"

        if self._should_skip(out_path):
            result.skipped += 1
            return

        tactic = tech.get("def_tactic_label", "")
        top = tech.get("top_def_tech_label", "")
        off_techniques = tech.get("off_techniques", [])

        lines = [f"# D3FEND: {name}", ""]
        if tactic:
            lines.append(f"**Tactic:** {tactic}")
        if top and top != name:
            lines.append(f"**Category:** {top}")
        lines.append("")

        if off_techniques:
            lines.append("## Counters ATT&CK Techniques")
            lines.append("")
            for off in sorted(set(off_techniques))[:20]:
                lines.append(f"- {off}")
            lines.append("")

        self._safe_write(out_path, "\n".join(lines))
        result.count += 1

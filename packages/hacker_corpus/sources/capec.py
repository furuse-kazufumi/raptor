"""
CAPEC (Common Attack Pattern Enumeration and Classification) fetcher.

Downloads the CAPEC XML from MITRE and converts each Attack Pattern
to a Markdown file for corpus2skill ingestion.

Rate limit: 0.5 seconds (single large download, then local parsing).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from packages.hacker_corpus.base import CorpusFetcher, FetchResult

_CAPEC_XML_URL = (
    "https://capec.mitre.org/data/xml/capec_latest.xml"
)
_TIMEOUT = 60  # Large XML file


# XML namespace used in CAPEC files
_NS = {
    "capec": "http://capec.mitre.org/capec-3",
    "attack": "http://capec.mitre.org/capec-3",
}


def _tag(ns_key: str, local: str) -> str:
    """Build a Clark-notation tag, e.g. {http://...}Attack_Pattern."""
    ns_map = {
        "capec": "http://capec.mitre.org/capec-3",
    }
    return f"{{{ns_map[ns_key]}}}{local}"


def _get_text(element: ET.Element | None, tag: str, ns: str = "capec") -> str:
    """Safely get text from a child element."""
    if element is None:
        return ""
    child = element.find(f"{{{_NS[ns]}}}{tag}")
    if child is None or child.text is None:
        return ""
    return child.text.strip()


class CAPECFetcher(CorpusFetcher):
    name = "capec"
    rate_limit = 0.5

    def __init__(self, output_dir: Path, force: bool = False) -> None:
        super().__init__(output_dir / "capec", force=force)

    def _do_fetch(self, result: FetchResult) -> None:
        xml_cache = self.output_dir / "_capec_latest.xml"

        # Download the XML (or use cached copy)
        if xml_cache.exists() and not self.force:
            raw_xml = xml_cache.read_bytes()
        else:
            try:
                resp = requests.get(_CAPEC_XML_URL, timeout=_TIMEOUT)
                resp.raise_for_status()
                raw_xml = resp.content
                self._safe_write(xml_cache, resp.text)
            except Exception as exc:
                result.errors.append(f"Failed to download CAPEC XML: {exc}")
                return

        try:
            root = ET.fromstring(raw_xml)
        except ET.ParseError as exc:
            result.errors.append(f"XML parse error: {exc}")
            return

        # CAPEC XML uses a dynamic namespace — discover it
        ns_prefix = ""
        tag = root.tag
        if tag.startswith("{"):
            ns_prefix = tag[1:tag.index("}")]

        def find_all_patterns(parent: ET.Element) -> list[ET.Element]:
            if ns_prefix:
                return parent.findall(f"{{{ns_prefix}}}Attack_Pattern")
            return parent.findall("Attack_Pattern")

        def child_text(el: ET.Element, name: str) -> str:
            child = el.find(f"{{{ns_prefix}}}{name}") if ns_prefix else el.find(name)
            if child is None or child.text is None:
                return ""
            return child.text.strip()

        def all_text(el: ET.Element) -> str:
            """Recursively collect all text content."""
            return " ".join(t.strip() for t in el.itertext() if t.strip())

        # Find Attack_Patterns container
        if ns_prefix:
            container = root.find(f"{{{ns_prefix}}}Attack_Patterns")
        else:
            container = root.find("Attack_Patterns")

        if container is None:
            # Some versions put patterns at root level
            container = root

        patterns = find_all_patterns(container)
        for pattern in patterns:
            self._convert_pattern(
                pattern, ns_prefix, child_text, all_text, result
            )

    def _convert_pattern(
        self,
        pattern: ET.Element,
        ns_prefix: str,
        child_text,
        all_text,
        result: FetchResult,
    ) -> None:
        capec_id = pattern.get("ID", "0")
        name = pattern.get("Name", f"CAPEC-{capec_id}")
        out_path = self.output_dir / f"CAPEC-{capec_id}.md"

        if self._should_skip(out_path):
            result.skipped += 1
            return

        def find(tag: str) -> ET.Element | None:
            if ns_prefix:
                return pattern.find(f"{{{ns_prefix}}}{tag}")
            return pattern.find(tag)

        description = ""
        desc_el = find("Description")
        if desc_el is not None:
            description = all_text(desc_el)

        execution_flow = ""
        exec_el = find("Execution_Flow")
        if exec_el is not None:
            execution_flow = all_text(exec_el)

        prerequisites = ""
        pre_el = find("Prerequisites")
        if pre_el is not None:
            prerequisites = all_text(pre_el)

        mitigations = ""
        mit_el = find("Mitigations")
        if mit_el is not None:
            mitigations = all_text(mit_el)

        likelihood = pattern.get("Likelihood_Of_Attack", "")
        severity = pattern.get("Typical_Severity", "")

        lines = [
            f"# CAPEC-{capec_id}: {name}",
            "",
            f"**Likelihood of Attack:** {likelihood}",
            f"**Typical Severity:** {severity}",
            "",
        ]

        if description:
            lines += ["## Description", "", description, ""]

        if execution_flow:
            lines += ["## Execution Flow", "", execution_flow, ""]

        if prerequisites:
            lines += ["## Prerequisites", "", prerequisites, ""]

        if mitigations:
            lines += ["## Mitigations", "", mitigations, ""]

        content = "\n".join(lines)
        self._safe_write(out_path, content)
        result.count += 1

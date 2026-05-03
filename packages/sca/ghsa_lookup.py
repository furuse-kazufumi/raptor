"""GHSA local database cross-reference for SCA findings.

Queries the locally fetched GHSA JSON files (D:/docs/hacker_corpus/ghsa/)
to enrich OSV findings with full advisory details.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


_GHSA_DIR: Optional[Path] = None


def _get_ghsa_dir() -> Optional[Path]:
    global _GHSA_DIR
    if _GHSA_DIR is not None:
        return _GHSA_DIR
    candidates = [
        Path(os.environ.get("RAPTOR_CORPUS_DIR", "D:/docs/hacker_corpus")) / "ghsa",
        Path("D:/docs/hacker_corpus/ghsa"),
    ]
    for c in candidates:
        if c.exists():
            _GHSA_DIR = c
            return _GHSA_DIR
    return None


def _build_index() -> dict[str, Path]:
    """Build a mapping from GHSA-ID and CVE aliases to file paths."""
    ghsa_dir = _get_ghsa_dir()
    if not ghsa_dir:
        return {}
    index: dict[str, Path] = {}
    for p in ghsa_dir.glob("GHSA-*.json"):
        ghsa_id = p.stem
        index[ghsa_id] = p
    return index


_INDEX: dict[str, Path] = {}
_INDEX_BUILT = False


def _ensure_index() -> None:
    global _INDEX, _INDEX_BUILT
    if not _INDEX_BUILT:
        _INDEX = _build_index()
        _INDEX_BUILT = True


def lookup_by_alias(aliases: list[str]) -> Optional[dict]:
    """Find a GHSA advisory by CVE or GHSA alias list from OSV.

    Returns the advisory dict or None if not found locally.
    """
    _ensure_index()
    if not _INDEX:
        return None

    for alias in aliases:
        if alias.startswith("GHSA-") and alias in _INDEX:
            try:
                return json.loads(_INDEX[alias].read_text(encoding="utf-8"))
            except Exception:
                pass

    # Fallback: scan for CVE in advisory references (slow, only if needed)
    cves = [a for a in aliases if a.startswith("CVE-")]
    if not cves:
        return None

    for path in _INDEX.values():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            refs = [r.get("url", "") for r in data.get("references", [])]
            for cve in cves:
                if any(cve in r for r in refs):
                    return data
        except Exception:
            continue
    return None


def enrich_vuln(vuln: dict) -> dict:
    """Add GHSA details to an OSV vuln dict.

    Adds 'ghsa' key with severity, cwes, and description excerpt when found.
    Returns the original dict (possibly enriched in-place).
    """
    aliases = vuln.get("aliases", [])
    advisory = lookup_by_alias(aliases)
    if not advisory:
        return vuln

    cwes = [c.get("cweId", "") for c in advisory.get("cwes", {}).get("nodes", [])]
    pkgs = advisory.get("vulnerabilities", {}).get("nodes", [])
    patched = [
        p.get("firstPatchedVersion", {}).get("identifier", "")
        for p in pkgs
        if p.get("firstPatchedVersion")
    ]

    vuln["ghsa"] = {
        "ghsa_id": advisory.get("ghsaId", ""),
        "severity": advisory.get("severity", ""),
        "description": (advisory.get("description", "")[:300] + "...") if advisory.get("description") else "",
        "cwes": [c for c in cwes if c],
        "patched_versions": [v for v in patched if v],
    }
    return vuln


def is_available() -> bool:
    """Return True if the local GHSA database is present."""
    return _get_ghsa_dir() is not None

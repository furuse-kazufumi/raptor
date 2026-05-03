"""OSV (Open Source Vulnerabilities) batch API lookup.

Queries https://api.osv.dev/v1/querybatch for known CVEs against a list of
(package, version, ecosystem) tuples.  No API key required.
"""
import json
import urllib.error
import urllib.request
from typing import Any

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_TIMEOUT = 30

ECOSYSTEM_BY_MANIFEST = {
    "requirements.txt": "PyPI",
    "pyproject.toml": "PyPI",
    "setup.py": "PyPI",
    "package.json": "npm",
    "package-lock.json": "npm",
    "pom.xml": "Maven",
    "build.gradle": "Maven",
    "Cargo.toml": "crates.io",
    "go.mod": "Go",
    "Gemfile": "RubyGems",
    "Gemfile.lock": "RubyGems",
    "composer.json": "Packagist",
    "nuget.config": "NuGet",
}


def lookup_batch(packages: list[dict[str, str]]) -> dict[str, list[dict]]:
    """Query OSV for multiple packages in a single request.

    Args:
        packages: list of {"name": str, "version": str, "ecosystem": str}

    Returns:
        dict mapping "ecosystem:name:version" → list of vuln dicts.
        Each vuln dict has: id, summary, severity, aliases.
        Returns {"_error": msg} on network failure.
    """
    if not packages:
        return {}

    queries = [
        {
            "package": {"name": p["name"], "ecosystem": p["ecosystem"]},
            "version": p.get("version", ""),
        }
        for p in packages
    ]
    payload = json.dumps({"queries": queries}).encode()
    req = urllib.request.Request(
        OSV_BATCH_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=OSV_TIMEOUT) as resp:
            data: dict[str, Any] = json.loads(resp.read())
    except urllib.error.URLError as e:
        return {"_error": f"network: {e}"}
    except Exception as e:
        return {"_error": str(e)}

    results: dict[str, list[dict]] = {}
    for i, result_set in enumerate(data.get("results", [])):
        if i >= len(packages):
            break
        pkg = packages[i]
        key = f"{pkg['ecosystem']}:{pkg['name']}:{pkg.get('version', '')}"
        vulns = result_set.get("vulns", [])
        if vulns:
            results[key] = [
                {
                    "id": v.get("id", ""),
                    "summary": v.get("summary", ""),
                    "severity": (
                        v.get("database_specific", {}).get("severity")
                        or _extract_cvss_severity(v)
                        or "UNKNOWN"
                    ),
                    "aliases": v.get("aliases", []),
                    "references": [r.get("url", "") for r in v.get("references", [])[:3]],
                }
                for v in vulns
            ]
    return results


def _extract_cvss_severity(vuln: dict) -> str | None:
    for sev in vuln.get("severity", []):
        score_str = sev.get("score", "")
        try:
            score = float(score_str.split("/")[0]) if "/" in score_str else float(score_str)
            if score >= 9.0:
                return "CRITICAL"
            elif score >= 7.0:
                return "HIGH"
            elif score >= 4.0:
                return "MEDIUM"
            else:
                return "LOW"
        except (ValueError, TypeError):
            continue
    return None


def format_vuln_table(results: dict[str, list[dict]]) -> str:
    """Return a compact text table of vulnerabilities."""
    if not results or "_error" in results:
        return results.get("_error", "No vulnerabilities found.")
    lines = []
    for pkg_key, vulns in sorted(results.items()):
        eco, name, ver = pkg_key.split(":", 2)
        lines.append(f"\n{name} {ver} ({eco})")
        for v in vulns:
            sev = v["severity"].ljust(8)
            lines.append(f"  [{sev}] {v['id']}  {v['summary'][:80]}")
    return "\n".join(lines) if lines else "No vulnerabilities found."

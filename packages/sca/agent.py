#!/usr/bin/env python3
"""RAPTOR SCA Agent
Inspects dependency manifests and queries OSV for known CVEs.

Supported manifests: pom.xml, build.gradle, package.json,
requirements.txt, pyproject.toml, Cargo.toml, go.mod
"""
import argparse
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from core.json import load_json, save_json
from packages.sca.ghsa_lookup import enrich_vuln, is_available as ghsa_available
from packages.sca.osv_lookup import ECOSYSTEM_BY_MANIFEST, lookup_batch


def get_out_dir() -> Path:
    import os
    base = os.environ.get("RAPTOR_OUT_DIR")
    return Path(base).resolve() if base else Path("out").resolve()


MANIFEST_PATTERNS = list(ECOSYSTEM_BY_MANIFEST.keys())


def find_dependency_files(root: Path) -> list[Path]:
    found = []
    for pat in MANIFEST_PATTERNS:
        for p in root.rglob(pat):
            if ".git" not in p.parts and "node_modules" not in p.parts:
                found.append(p)
    return found


def parse_pom(p: Path) -> list[dict]:
    try:
        tree = ET.parse(p)
        root = tree.getroot()
        ns = {"m": "http://maven.apache.org/POM/4.0.0"}
        deps = []
        for d in root.findall(".//m:dependency", ns):
            g = d.find("m:groupId", ns)
            a = d.find("m:artifactId", ns)
            v = d.find("m:version", ns)
            name = f"{g.text}:{a.text}" if g is not None and a is not None else (a.text if a is not None else "unknown")
            deps.append({"name": name, "version": v.text if v is not None else "", "ecosystem": "Maven"})
        return deps
    except Exception as e:
        return [{"error": str(e)}]


def parse_requirements(p: Path) -> list[dict]:
    deps = []
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or ln.startswith("-"):
            continue
        # handle name==ver, name>=ver, name~=ver
        for sep in ("==", ">=", "<=", "~=", "!=", ">", "<"):
            if sep in ln:
                name, _, ver = ln.partition(sep)
                deps.append({"name": name.strip(), "version": ver.split(",")[0].strip(), "ecosystem": "PyPI"})
                break
        else:
            deps.append({"name": ln, "version": "", "ecosystem": "PyPI"})
    return deps


def parse_package_json(p: Path) -> list[dict]:
    try:
        obj = load_json(p)
        if not isinstance(obj, dict):
            return [{"error": "invalid JSON"}]
        deps = []
        for section in ("dependencies", "devDependencies"):
            for name, ver in obj.get(section, {}).items():
                ver = ver.lstrip("^~>=<")
                deps.append({"name": name, "version": ver, "ecosystem": "npm"})
        return deps
    except Exception as e:
        return [{"error": str(e)}]


def parse_cargo_toml(p: Path) -> list[dict]:
    deps = []
    try:
        import re
        text = p.read_text(encoding="utf-8", errors="replace")
        in_deps = False
        for ln in text.splitlines():
            ln = ln.strip()
            if ln in ("[dependencies]", "[dev-dependencies]", "[build-dependencies]"):
                in_deps = True
                continue
            if ln.startswith("[") and not ln.startswith("[dep"):
                in_deps = False
            if not in_deps:
                continue
            m = re.match(r'^(\w[\w-]*)\s*=\s*["\']([^"\']+)["\']', ln)
            if m:
                deps.append({"name": m.group(1), "version": m.group(2), "ecosystem": "crates.io"})
            m2 = re.match(r'^(\w[\w-]*)\s*=\s*\{.*version\s*=\s*["\']([^"\']+)["\']', ln)
            if m2:
                deps.append({"name": m2.group(1), "version": m2.group(2), "ecosystem": "crates.io"})
    except Exception as e:
        deps.append({"error": str(e)})
    return deps


def parse_go_mod(p: Path) -> list[dict]:
    deps = []
    try:
        in_require = False
        for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
            ln = ln.strip()
            if ln == "require (":
                in_require = True
                continue
            if in_require and ln == ")":
                in_require = False
                continue
            if ln.startswith("require "):
                ln = ln[8:]
            if in_require or True:
                parts = ln.split()
                if len(parts) >= 2 and "/" in parts[0]:
                    deps.append({"name": parts[0], "version": parts[1].lstrip("v"), "ecosystem": "Go"})
    except Exception as e:
        deps.append({"error": str(e)})
    return deps


PARSERS = {
    "pom.xml": parse_pom,
    "requirements.txt": parse_requirements,
    "pyproject.toml": parse_requirements,  # simplified: reads [project.dependencies]
    "package.json": parse_package_json,
    "Cargo.toml": parse_cargo_toml,
    "go.mod": parse_go_mod,
}


def build_osv_packages(files_data: list[dict]) -> list[dict]:
    """Flatten all parsed deps across all manifests into a deduplicated list."""
    seen = set()
    pkgs = []
    for entry in files_data:
        for dep in entry.get("deps", []):
            if "error" in dep:
                continue
            key = (dep["ecosystem"], dep["name"], dep.get("version", ""))
            if key not in seen:
                seen.add(key)
                pkgs.append({"name": dep["name"], "version": dep.get("version", ""), "ecosystem": dep["ecosystem"]})
    return pkgs


def main():
    ap = argparse.ArgumentParser(description="RAPTOR SCA Agent — dependency + OSV CVE scan")
    ap.add_argument("--repo", required=True, help="Path to repository root")
    ap.add_argument("--out", default=None, help="Output directory")
    ap.add_argument("--no-osv", action="store_true", help="Skip OSV network lookup")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.exists():
        print(f"ERROR: repo not found: {repo}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out).resolve() if args.out else get_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Collect manifests
    manifest_files = find_dependency_files(repo)
    files_data = []
    for p in manifest_files:
        parser = PARSERS.get(p.name)
        entry: dict = {"path": str(p.relative_to(repo)), "manifest": p.name}
        if parser:
            entry["deps"] = parser(p)
        else:
            entry["note"] = "unsupported parser"
            entry["deps"] = []
        files_data.append(entry)

    total_deps = sum(len(e.get("deps", [])) for e in files_data)
    print(f"[SCA] Found {len(manifest_files)} manifest(s), {total_deps} dependency entries", flush=True)

    # 2. OSV lookup
    vuln_results: dict = {}
    if not args.no_osv and total_deps > 0:
        print("[SCA] Querying OSV database...", flush=True)
        packages = build_osv_packages(files_data)
        if packages:
            vuln_results = lookup_batch(packages)
            if "_error" in vuln_results:
                print(f"[SCA] OSV query failed: {vuln_results['_error']}", file=sys.stderr)
            else:
                vuln_count = sum(len(v) for v in vuln_results.values())
                print(f"[SCA] OSV: {vuln_count} vulnerability/vulnerabilities found in {len(vuln_results)} package(s)", flush=True)

    # 2b. GHSA enrichment (local cross-reference)
    if vuln_results and not args.no_osv and ghsa_available():
        print("[SCA] Cross-referencing with local GHSA database...", flush=True)
        enriched = 0
        for key, vulns in vuln_results.items():
            if key.startswith("_"):
                continue
            for v in vulns:
                original_len = len(v)
                enrich_vuln(v)
                if len(v) > original_len:
                    enriched += 1
        if enriched:
            print(f"[SCA] GHSA: enriched {enriched} finding(s) with advisory details", flush=True)

    # 3. Build output
    result = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repo": str(repo),
        "manifest_files": len(manifest_files),
        "total_deps": total_deps,
        "files": files_data,
        "vulnerabilities": vuln_results,
        "summary": {
            "vulnerable_packages": len([k for k in vuln_results if not k.startswith("_")]),
            "total_cves": sum(len(v) for k, v in vuln_results.items() if not k.startswith("_")),
        },
    }

    out_file = out_dir / "sca_report.json"
    save_json(out_file, result)
    print(f"[SCA] Report written to {out_file}")
    print(json.dumps({
        "status": "ok",
        "manifest_files": len(manifest_files),
        "deps": total_deps,
        "vulnerable_packages": result["summary"]["vulnerable_packages"],
        "total_cves": result["summary"]["total_cves"],
    }))


if __name__ == "__main__":
    main()

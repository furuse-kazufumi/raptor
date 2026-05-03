#!/usr/bin/env python3
"""RAPTOR SCA — Software Composition Analysis with OSV CVE lookup.

Scans a repository for dependency manifests (requirements.txt, package.json,
pom.xml, Cargo.toml, go.mod, etc.) and queries the OSV database for known
vulnerabilities in each dependency.

Usage:
    python3 raptor_sca.py --repo /path/to/target [--out <dir>] [--no-osv]
    python3 raptor.py sca --repo /path/to/target
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.config import RaptorConfig
from core.logging import get_logger
from core.run import get_output_dir, start_run, complete_run, fail_run
from packages.sca.agent import find_dependency_files, PARSERS, build_osv_packages
from packages.sca.osv_lookup import lookup_batch, format_vuln_table

import json
import time

logger = get_logger()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="RAPTOR SCA — dependency inventory + OSV CVE lookup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--repo", required=True, metavar="PATH", help="Repository root to scan")
    p.add_argument("--out", default=None, metavar="DIR", help="Output directory (default: auto)")
    p.add_argument("--no-osv", action="store_true", help="Skip OSV network lookup (inventory only)")
    return p


def main() -> int:
    args = build_parser().parse_args()
    repo = Path(args.repo).resolve()
    if not repo.exists():
        logger.error("repo not found: %s", repo)
        return 1

    # Resolve output directory
    try:
        out_dir = get_output_dir("sca", target_path=str(repo),
                                  explicit_out=args.out)
    except Exception as e:
        logger.error("output dir error: %s", e)
        return 1

    start_run(out_dir, "sca", target=str(repo))
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        rc = _run(repo, out_dir, args)
    except Exception as e:
        logger.exception("SCA failed: %s", e)
        fail_run(out_dir, error=str(e))
        return 1

    if rc == 0:
        complete_run(out_dir)
    else:
        fail_run(out_dir, error=f"exit code {rc}")
    return rc


def _run(repo: Path, out_dir: Path, args: argparse.Namespace) -> int:
    from core.json import save_json

    # 1. Find manifests
    manifest_files = find_dependency_files(repo)
    if not manifest_files:
        print("[SCA] No dependency manifests found.")
        save_json(out_dir / "sca_report.json", {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "repo": str(repo), "manifest_files": 0, "total_deps": 0,
            "files": [], "vulnerabilities": {}, "summary": {"vulnerable_packages": 0, "total_cves": 0},
        })
        return 0

    # 2. Parse each manifest
    files_data = []
    for p in manifest_files:
        parser_fn = PARSERS.get(p.name)
        entry = {"path": str(p.relative_to(repo)), "manifest": p.name}
        if parser_fn:
            entry["deps"] = parser_fn(p)
        else:
            entry["deps"] = []
            entry["note"] = "unsupported parser"
        files_data.append(entry)

    total_deps = sum(len(e.get("deps", [])) for e in files_data)
    print(f"[SCA] {len(manifest_files)} manifest(s), {total_deps} dependencies", flush=True)

    # 3. OSV lookup
    vuln_results: dict = {}
    if not args.no_osv:
        packages = build_osv_packages(files_data)
        print(f"[SCA] Querying OSV for {len(packages)} unique packages...", flush=True)
        if packages:
            vuln_results = lookup_batch(packages)
            if "_error" in vuln_results:
                print(f"[SCA] OSV error: {vuln_results['_error']}", flush=True)
            else:
                n_vuln = len(vuln_results)
                n_cve = sum(len(v) for v in vuln_results.values())
                print(f"[SCA] OSV: {n_cve} CVE(s) across {n_vuln} vulnerable package(s)", flush=True)

    # 4. Build and save report
    summary = {
        "vulnerable_packages": len([k for k in vuln_results if not k.startswith("_")]),
        "total_cves": sum(len(v) for k, v in vuln_results.items() if not k.startswith("_")),
    }
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repo": str(repo),
        "manifest_files": len(manifest_files),
        "total_deps": total_deps,
        "files": files_data,
        "vulnerabilities": vuln_results,
        "summary": summary,
    }
    out_file = out_dir / "sca_report.json"
    save_json(out_file, report)

    # 5. Human-readable summary
    print(f"\n{'='*60}")
    print(f"SCA Report: {repo.name}")
    print(f"{'='*60}")
    print(f"Manifests:            {len(manifest_files)}")
    print(f"Dependencies:         {total_deps}")
    print(f"Vulnerable packages:  {summary['vulnerable_packages']}")
    print(f"Total CVEs:           {summary['total_cves']}")
    if vuln_results and "_error" not in vuln_results:
        print(format_vuln_table(vuln_results))
    print(f"\nFull report: {out_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

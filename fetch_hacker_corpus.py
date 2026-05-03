#!/usr/bin/env python3
"""
Fetch practical security knowledge from public hacker/security communities.

Sources (all free, no API key required):
  1. Exploit-DB   — CVE-linked exploits/PoCs (~50,000 entries, GitLab CSV)
  2. NVD/NIST     — High/Critical CVEs with descriptions (public REST API)
  3. MITRE ATT&CK — Tactics, techniques, procedures (GitHub JSON)

Usage:
    python3 fetch_hacker_corpus.py --output tmp_hacker_corpus
    python3 fetch_hacker_corpus.py --output tmp_hacker_corpus --resume
    python3 fetch_hacker_corpus.py --output tmp_hacker_corpus --only exploitdb
"""
import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

EXPLOITDB_CSV  = "https://gitlab.com/exploit-database/exploitdb/-/raw/main/files_exploits.csv"
EXPLOITDB_RAW  = "https://gitlab.com/exploit-database/exploitdb/-/raw/main/"
NVD_API        = "https://services.nvd.nist.gov/rest/json/cves/2.0"
ATTCK_INDEX    = "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json"

NVD_RATE       = 6.5   # seconds between NVD requests (free tier: 5 req/30s)
EXPLOITDB_RATE = 1.0   # seconds between exploit file fetches

CORPUS2SKILL_NAME = "hacker_corpus"
CORPUS2SKILL_ARGS = ["--max-depth", "3", "--min-cluster-size", "10",
                     "--max-clusters", "8", "--overwrite"]


# ─── Resume helpers (O(1) lookup, built once per source) ────────────────────

def _load_existing_ids(out_dir: Path, src_prefix: str) -> set:
    """Scan out_dir once and return set of doc_ids already saved."""
    ids = set()
    if src_prefix == "edb":
        for f in out_dir.glob("edb_*.md"):
            m = re.match(r"^(edb_\d{6})_", f.name)
            if m:
                ids.add(m.group(1))
    elif src_prefix == "attck":
        for f in out_dir.glob("attck_*.md"):
            m = re.match(r"^(attck_[A-Z]\d+(?:_\d+)?)_", f.name)
            if m:
                ids.add(m.group(1))
    elif src_prefix == "nvd":
        for f in out_dir.glob("nvd_*.md"):
            m = re.match(r"^(nvd_CVE_\d{4}_\d+)_", f.name)
            if m:
                ids.add(m.group(1))
    return ids


# ─── Exploit-DB ─────────────────────────────────────────────────────────────

def fetch_exploitdb(out_dir: Path, resume: bool) -> int:
    """Download Exploit-DB CSV and convert each entry to markdown."""
    print("\n[exploitdb] Downloading CSV (~10MB) ...", flush=True)
    try:
        req = Request(EXPLOITDB_CSV, headers={"User-Agent": "Python/security-corpus-builder"})
        with urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", errors="replace")
    except URLError as e:
        print(f"[exploitdb] ERROR: {e}", flush=True)
        return 0

    reader = csv.DictReader(io.StringIO(raw))
    saved = 0
    skipped = 0
    fetch_errors = 0
    existing = _load_existing_ids(out_dir, "edb") if resume else set()

    for row in reader:
        eid      = row.get("id", "").strip()
        filepath = row.get("file", "").strip()          # e.g. exploits/linux/local/12345.txt
        desc     = row.get("description", "").strip()
        date     = row.get("date_published", row.get("date_added", "")).strip()
        author   = row.get("author", "").strip()
        etype    = row.get("type", "").strip()          # remote/local/dos/webapps
        platform = row.get("platform", "").strip()
        codes    = row.get("codes", "").strip()         # CVE references

        if not eid or not desc:
            continue

        doc_id = f"edb_{eid.zfill(6)}"

        if resume and doc_id in existing:
            skipped += 1
            continue

        # Try to fetch the exploit source file (text exploits only, skip binaries)
        exploit_code = ""
        if filepath and not filepath.endswith((".zip", ".gz", ".tar", ".exe", ".bin")):
            time.sleep(EXPLOITDB_RATE)
            url = EXPLOITDB_RAW + filepath
            try:
                req2 = Request(url, headers={"User-Agent": "Python/security-corpus-builder"})
                with urlopen(req2, timeout=20) as r:
                    raw_code = r.read()
                    exploit_code = raw_code.decode("utf-8", errors="replace")[:3000]
            except (URLError, HTTPError):
                fetch_errors += 1

        # Build markdown
        cve_line = f"**CVE:** {codes}" if codes else ""
        code_block = f"\n```\n{exploit_code[:2000]}\n```" if exploit_code.strip() else ""

        md = (
            f"# {desc}\n\n"
            f"**Source:** Exploit-DB #{eid}\n"
            f"**Date:** {date}\n"
            f"**Author:** {author}\n"
            f"**Type:** {etype} / {platform}\n"
            f"{cve_line}\n"
            f"**URL:** https://www.exploit-db.com/exploits/{eid}\n\n"
            f"## Description\n\n{desc}\n"
            f"{code_block}\n"
        )

        safe = re.sub(r"[^\w\s-]", "", desc)
        safe = re.sub(r"\s+", "_", safe.strip())[:50].strip("_") or "exploit"
        fname = f"{doc_id}_{safe}.md"
        (out_dir / fname).write_text(md, encoding="utf-8")
        saved += 1

        if saved % 1000 == 0:
            print(f"[exploitdb]   {saved:,} saved  {fetch_errors} fetch-errors ...", flush=True)

    print(f"[exploitdb] Done: {saved:,} saved, {skipped} skipped, {fetch_errors} fetch errors", flush=True)
    return saved


def fetch_exploitdb_metaonly(out_dir: Path, resume: bool) -> int:
    """Faster variant: metadata only, no individual file downloads."""
    print("\n[exploitdb] Downloading CSV (metadata only, fast mode) ...", flush=True)
    try:
        req = Request(EXPLOITDB_CSV, headers={"User-Agent": "Python/security-corpus-builder"})
        with urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", errors="replace")
    except URLError as e:
        print(f"[exploitdb] ERROR: {e}", flush=True)
        return 0

    reader = csv.DictReader(io.StringIO(raw))
    saved = 0
    existing = _load_existing_ids(out_dir, "edb") if resume else set()

    for row in reader:
        eid      = row.get("id", "").strip()
        desc     = row.get("description", "").strip()
        date     = row.get("date_published", row.get("date_added", "")).strip()
        author   = row.get("author", "").strip()
        etype    = row.get("type", "").strip()
        platform = row.get("platform", "").strip()
        codes    = row.get("codes", "").strip()
        tags     = row.get("tags", "").strip()
        verified = row.get("verified", "").strip()

        if not eid or not desc:
            continue

        doc_id = f"edb_{eid.zfill(6)}"
        if resume and doc_id in existing:
            continue

        cve_line = f"\n**CVE:** {codes}" if codes else ""
        tag_line = f"\n**Tags:** {tags}" if tags else ""

        md = (
            f"# {desc}\n\n"
            f"**Source:** Exploit-DB #{eid}\n"
            f"**Date:** {date}\n"
            f"**Author:** {author}\n"
            f"**Type:** {etype} / {platform}\n"
            f"**Verified:** {verified}"
            f"{cve_line}{tag_line}\n"
            f"**URL:** https://www.exploit-db.com/exploits/{eid}\n\n"
            f"## About\n\n"
            f"This is a {'verified ' if verified=='1' else ''}{etype} exploit targeting {platform}. "
            f"{desc}."
            f"{(' CVE references: ' + codes + '.') if codes else ''}"
            f"{(' Tags: ' + tags + '.') if tags else ''}\n"
        )

        safe = re.sub(r"[^\w\s-]", "", desc)
        safe = re.sub(r"\s+", "_", safe.strip())[:50].strip("_") or "exploit"
        (out_dir / f"{doc_id}_{safe}.md").write_text(md, encoding="utf-8")
        saved += 1

        if saved % 2000 == 0:
            print(f"[exploitdb]   {saved:,} entries processed ...", flush=True)

    print(f"[exploitdb] Done: {saved:,} saved", flush=True)
    return saved


# ─── NVD / NIST ─────────────────────────────────────────────────────────────

def fetch_nvd(out_dir: Path, resume: bool, severity: str = "HIGH,CRITICAL") -> int:
    """Fetch High/Critical CVEs from NVD REST API (no key needed, rate-limited)."""
    print(f"\n[nvd] Fetching {severity} CVEs from NVD ...", flush=True)
    saved = 0
    start_index = 0
    results_per_page = 2000
    existing = _load_existing_ids(out_dir, "nvd") if resume else set()
    print(f"[nvd] Resume: {len(existing):,} already saved", flush=True)

    while True:
        params = {
            "resultsPerPage": results_per_page,
            "startIndex":     start_index,
            "cvssV3Severity": "CRITICAL",   # fetch CRITICAL first
        }
        # NVD doesn't support multi-severity in one call; we'll do two passes
        url = f"{NVD_API}?{urlencode(params)}"
        try:
            req = Request(url, headers={"User-Agent": "Python/security-corpus-builder"})
            with urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
        except (URLError, HTTPError) as e:
            print(f"[nvd] Request error at startIndex={start_index}: {e}", flush=True)
            time.sleep(30)
            continue

        vulns = data.get("vulnerabilities", [])
        if not vulns:
            break

        for item in vulns:
            cve = item.get("cve", {})
            cve_id = cve.get("id", "")
            if not cve_id:
                continue

            doc_id = f"nvd_{cve_id.replace('-', '_')}"
            if resume and doc_id in existing:
                continue

            # Description
            descs = cve.get("descriptions", [])
            desc_en = next((d["value"] for d in descs if d.get("lang") == "en"), "")
            if not desc_en or len(desc_en) < 30:
                continue

            # Metrics
            metrics = cve.get("metrics", {})
            cvss3 = metrics.get("cvssMetricV31", metrics.get("cvssMetricV30", []))
            score = ""
            vector = ""
            if cvss3:
                cvss_data = cvss3[0].get("cvssData", {})
                score  = str(cvss_data.get("baseScore", ""))
                vector = cvss_data.get("vectorString", "")

            published = cve.get("published", "")[:10]
            modified  = cve.get("lastModified", "")[:10]

            # References
            refs = cve.get("references", [])
            ref_lines = "\n".join(f"- {r['url']}" for r in refs[:5])

            # Weaknesses (CWE)
            weaknesses = cve.get("weaknesses", [])
            cwes = []
            for w in weaknesses:
                for d in w.get("description", []):
                    if d.get("lang") == "en":
                        cwes.append(d["value"])

            md = (
                f"# {cve_id}\n\n"
                f"**Source:** NVD/NIST\n"
                f"**Published:** {published}\n"
                f"**Modified:** {modified}\n"
                f"**CVSS Score:** {score}\n"
                f"**Vector:** {vector}\n"
                f"**CWE:** {', '.join(cwes)}\n"
                f"**URL:** https://nvd.nist.gov/vuln/detail/{cve_id}\n\n"
                f"## Description\n\n{desc_en}\n\n"
                f"## References\n\n{ref_lines}\n"
            )

            safe = re.sub(r"[^\w-]", "_", cve_id)
            (out_dir / f"{doc_id}_{safe}.md").write_text(md, encoding="utf-8")
            existing.add(doc_id)
            saved += 1

        total = data.get("totalResults", 0)
        start_index += len(vulns)
        print(f"[nvd]   {saved:,} saved ({start_index}/{total}) ...", flush=True)

        if start_index >= total:
            break

        time.sleep(NVD_RATE)

    # Second pass: HIGH severity (reuse existing set, already updated by CRITICAL pass)
    print("[nvd] Fetching HIGH severity CVEs ...", flush=True)
    start_index = 0
    while True:
        params = {
            "resultsPerPage": results_per_page,
            "startIndex":     start_index,
            "cvssV3Severity": "HIGH",
        }
        url = f"{NVD_API}?{urlencode(params)}"
        try:
            req = Request(url, headers={"User-Agent": "Python/security-corpus-builder"})
            with urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
        except (URLError, HTTPError) as e:
            print(f"[nvd] HIGH request error: {e}", flush=True)
            time.sleep(30)
            continue

        vulns = data.get("vulnerabilities", [])
        if not vulns:
            break

        for item in vulns:
            cve = item.get("cve", {})
            cve_id = cve.get("id", "")
            if not cve_id:
                continue
            doc_id = f"nvd_{cve_id.replace('-', '_')}"
            if doc_id in existing:
                continue  # already saved from CRITICAL pass or resume

            descs = cve.get("descriptions", [])
            desc_en = next((d["value"] for d in descs if d.get("lang") == "en"), "")
            if not desc_en or len(desc_en) < 30:
                continue

            metrics = cve.get("metrics", {})
            cvss3 = metrics.get("cvssMetricV31", metrics.get("cvssMetricV30", []))
            score = ""
            vector = ""
            if cvss3:
                cvss_data = cvss3[0].get("cvssData", {})
                score  = str(cvss_data.get("baseScore", ""))
                vector = cvss_data.get("vectorString", "")

            published = cve.get("published", "")[:10]
            refs = cve.get("references", [])
            ref_lines = "\n".join(f"- {r['url']}" for r in refs[:5])
            weaknesses = cve.get("weaknesses", [])
            cwes = [d["value"] for w in weaknesses for d in w.get("description", []) if d.get("lang") == "en"]

            md = (
                f"# {cve_id}\n\n"
                f"**Source:** NVD/NIST\n"
                f"**Published:** {published}\n"
                f"**CVSS Score:** {score}\n"
                f"**Vector:** {vector}\n"
                f"**CWE:** {', '.join(cwes)}\n"
                f"**URL:** https://nvd.nist.gov/vuln/detail/{cve_id}\n\n"
                f"## Description\n\n{desc_en}\n\n"
                f"## References\n\n{ref_lines}\n"
            )

            safe = re.sub(r"[^\w-]", "_", cve_id)
            (out_dir / f"{doc_id}_{safe}.md").write_text(md, encoding="utf-8")
            existing.add(doc_id)
            saved += 1

        total = data.get("totalResults", 0)
        start_index += len(vulns)
        print(f"[nvd]   {saved:,} saved total ({start_index}/{total}) ...", flush=True)

        if start_index >= total:
            break

        time.sleep(NVD_RATE)

    print(f"[nvd] Done: {saved:,} CVEs saved", flush=True)
    return saved


# ─── MITRE ATT&CK ───────────────────────────────────────────────────────────

def fetch_attck(out_dir: Path, resume: bool) -> int:
    """Fetch MITRE ATT&CK Enterprise techniques from GitHub STIX bundle."""
    print("\n[attck] Downloading ATT&CK Enterprise STIX bundle ...", flush=True)
    try:
        req = Request(ATTCK_INDEX, headers={"User-Agent": "Python/security-corpus-builder"})
        with urlopen(req, timeout=120) as r:
            bundle = json.loads(r.read())
    except URLError as e:
        print(f"[attck] ERROR: {e}", flush=True)
        return 0

    objects = bundle.get("objects", [])
    saved = 0
    existing = _load_existing_ids(out_dir, "attck") if resume else set()

    for obj in objects:
        obj_type = obj.get("type", "")
        if obj_type not in ("attack-pattern", "course-of-action", "malware", "tool"):
            continue

        name = obj.get("name", "").strip()
        desc = obj.get("description", "").strip()
        if not name or not desc or len(desc) < 50:
            continue

        # Get ATT&CK ID (e.g. T1059)
        ext_refs = obj.get("external_references", [])
        attck_id = ""
        attck_url = ""
        for ref in ext_refs:
            if ref.get("source_name") == "mitre-attack":
                attck_id  = ref.get("external_id", "")
                attck_url = ref.get("url", "")
                break

        if not attck_id:
            continue

        doc_id = f"attck_{attck_id.replace('.', '_')}"
        if resume and doc_id in existing:
            continue

        # Kill chain phases
        phases = [p.get("phase_name", "") for p in obj.get("kill_chain_phases", [])]
        phase_str = ", ".join(phases)

        # Platforms
        platforms = ", ".join(obj.get("x_mitre_platforms", []))

        # Detection
        detection = obj.get("x_mitre_detection", "")

        md = (
            f"# {attck_id}: {name}\n\n"
            f"**Source:** MITRE ATT&CK Enterprise\n"
            f"**Type:** {obj_type}\n"
            f"**Tactic:** {phase_str}\n"
            f"**Platforms:** {platforms}\n"
            f"**URL:** {attck_url}\n\n"
            f"## Description\n\n{desc}\n"
        )
        if detection:
            md += f"\n## Detection\n\n{detection}\n"

        safe = re.sub(r"[^\w\s-]", "", name)
        safe = re.sub(r"\s+", "_", safe.strip())[:50].strip("_") or "technique"
        (out_dir / f"{doc_id}_{safe}.md").write_text(md, encoding="utf-8")
        saved += 1

    print(f"[attck] Done: {saved} techniques/tools/mitigations saved", flush=True)
    return saved


# ─── Main ────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fetch practical security knowledge (Exploit-DB + NVD + ATT&CK)"
    )
    p.add_argument("--output",  default="tmp_hacker_corpus", metavar="DIR")
    p.add_argument("--resume",  action="store_true")
    p.add_argument("--only",    default="all",
                   help="exploitdb | nvd | attck | all (default: all)")
    p.add_argument("--exploitdb-full", action="store_true",
                   help="Also download exploit source files (slower, ~50k HTTP requests)")
    p.add_argument("--skip-corpus2skill", action="store_true")
    return p


def main() -> int:
    args = build_parser().parse_args()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    total = 0
    only  = args.only.lower()

    print(f"[hacker-fetch] Output : {out_dir.resolve()}", flush=True)
    print(f"[hacker-fetch] Sources: {only}", flush=True)

    if only in ("all", "exploitdb"):
        if args.exploitdb_full:
            total += fetch_exploitdb(out_dir, args.resume)
        else:
            total += fetch_exploitdb_metaonly(out_dir, args.resume)

    if only in ("all", "attck"):
        total += fetch_attck(out_dir, args.resume)

    if only in ("all", "nvd"):
        total += fetch_nvd(out_dir, args.resume)

    elapsed = time.monotonic() - t0
    n_files  = len(list(out_dir.glob("*.md")))
    print(f"\n{'='*60}", flush=True)
    print(f"Hacker corpus fetch complete", flush=True)
    print(f"New this run : {total:,}", flush=True)
    print(f"Total in dir : {n_files:,}", flush=True)
    print(f"Elapsed      : {elapsed/60:.1f} min", flush=True)

    if not args.skip_corpus2skill:
        print(f"\n[hacker-fetch] Running Corpus2Skill on {n_files:,} documents ...", flush=True)
        raptor_root = Path(__file__).parent
        cmd = [
            sys.executable, str(raptor_root / "raptor_corpus2skill.py"),
            "--source", str(out_dir),
            "--name",   CORPUS2SKILL_NAME,
            *CORPUS2SKILL_ARGS,
        ]
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "RAPTOR_DIR": str(raptor_root)}
        result = subprocess.run(cmd, env=env)
        return result.returncode

    return 0


if __name__ == "__main__":
    sys.exit(main())

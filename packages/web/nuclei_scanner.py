"""Nuclei template scanner integration for RAPTOR web scans."""
from __future__ import annotations

import shutil
import subprocess
import json
from pathlib import Path


def is_available() -> bool:
    return bool(shutil.which("nuclei"))


def scan(target_url: str, out_dir: Path, severity: str = "medium,high,critical") -> list[dict]:
    """Run nuclei against target_url. Returns list of finding dicts."""
    if not is_available():
        return []

    out_file = out_dir / "nuclei_findings.json"
    cmd = [
        "nuclei", "-u", target_url,
        "-severity", severity,
        "-json-export", str(out_file),
        "-silent", "-no-color",
    ]
    try:
        subprocess.run(cmd, timeout=300, capture_output=True)
    except Exception:
        return []

    findings = []
    if out_file.exists():
        for line in out_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                findings.append(json.loads(line))
            except Exception:
                pass
    return findings

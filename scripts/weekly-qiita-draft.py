#!/usr/bin/env python3
"""Weekly NAS -> Qiita draft wrapper: collect -> build -> dry-run.

Self-contained. Chains three independent stages, each in its own repo, and
stops at the first failure:

  1. collect_nas_material.py   (llcore)    nas_pareto.json* -> numbers-only result.md
  2. build_qiita_draft.py      (llcore)    result.md -> Qiita draft markdown
  3. qiita_public_post.py dry-run (fullsense)  validate the draft is registration-safe

Fail-closed:
  - 0 runs collected            -> stop non-zero (never write an empty article).
  - dry-run reports findings     -> KEEP the draft, exit non-zero (do not publish).
  - any stage exits non-zero     -> stop and surface the reason.

Token-free: only `dry-run` is used (no live preflight). Publishing
(`qiita_public_post.py post <file> --yes`) stays a deliberate human step.

Paths are passed as subprocess list-args (never interpolated into a shell
string). Repo locations default to this machine's layout and are overridable
via env: LLCORE_DIR, FULLSENSE_DIR.

Usage:
  py -3.11 scripts/weekly-qiita-draft.py
  py -3.11 scripts/weekly-qiita-draft.py --roots C:/dev/projects/llcore/out --date 2026-08-01
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

RAPTOR_DIR = Path(__file__).resolve().parents[1]
LLCORE_DIR = Path(os.environ.get("LLCORE_DIR", "C:/dev/projects/llcore"))
FULLSENSE_DIR = Path(os.environ.get("FULLSENSE_DIR", "C:/dev/projects/fullsense"))

COLLECT = LLCORE_DIR / "scripts" / "collect_nas_material.py"
BUILD = LLCORE_DIR / "scripts" / "build_qiita_draft.py"
POSTER = FULLSENSE_DIR / "tools" / "qiita_public_post.py"

# Default roots point at raptor's worklog output, where orchestrated sweeps land
# (out/worklog/nas-*-r2/nas_pareto.json). That is the canonical, clean set — the
# llcore `out/` tree also holds smoke/dev iterations (nas_pareto_v2smoke, etc.)
# that would pollute a weekly report. Pass --roots to override (relative roots are
# resolved against LLCORE_DIR, where collect runs). The generator strips paths.
DEFAULT_ROOTS = str(RAPTOR_DIR / "out" / "worklog")
DEFAULT_WORKDIR = RAPTOR_DIR / "out" / "worklog" / "nas-weekly"
DEFAULT_DRAFT = FULLSENSE_DIR / "docs" / "articles" / "drafts" / "QIITA_nas_weekly.md"

_DRY_RUN_OK = "registration-safe: no findings"


def _run(
    argv: list[str], *, capture: bool = False, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a stage as a list-arg subprocess (no shell interpolation)."""
    return subprocess.run(
        argv, capture_output=capture, text=True, check=False,
        cwd=str(cwd) if cwd else None,
    )


def _fail(stage: str, code: int, detail: str = "") -> int:
    print(f"[weekly-qiita-draft] {stage} FAILED (exit {code})")
    if detail.strip():
        print(detail.rstrip())
    return code or 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--roots", nargs="*", default=[DEFAULT_ROOTS],
                    help="dirs scanned recursively for nas_pareto.json "
                         "(default: raptor out/worklog canonical sweeps; "
                         "relative overrides resolve against LLCORE_DIR)")
    ap.add_argument("--out", default=str(DEFAULT_DRAFT), help="draft markdown to write")
    ap.add_argument("--workdir", default=str(DEFAULT_WORKDIR),
                    help="where the intermediate result.md goes")
    ap.add_argument("--date", default=None, help="report date (YYYY-MM-DD); default today")
    a = ap.parse_args()

    for label, path in (("collect", COLLECT), ("build", BUILD), ("poster", POSTER)):
        if not path.exists():
            return _fail("preflight", 2, f"missing {label} script: {path}")

    workdir = Path(a.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    material = workdir / "result.md"
    draft = Path(a.out)
    py = sys.executable

    # --- stage 1: collect -------------------------------------------------- #
    collect_argv = [py, str(COLLECT), "--out", str(material), "--roots", *a.roots]
    print(f"[weekly-qiita-draft] collect -> {material}")
    r = _run(collect_argv, cwd=LLCORE_DIR)
    if r.returncode != 0:
        return _fail("collect", r.returncode)

    # 0 runs -> refuse to build an empty article (fail-closed).
    text = material.read_text(encoding="utf-8") if material.exists() else ""
    if "Runs found: 0" in text or not text.strip():
        return _fail("collect", 3, "0 runs collected — nothing to write")

    # --- stage 2: build ---------------------------------------------------- #
    build_argv = [py, str(BUILD), "--material", str(material), "--out", str(draft)]
    if a.date:
        build_argv += ["--date", a.date]
    print(f"[weekly-qiita-draft] build -> {draft}")
    r = _run(build_argv)
    if r.returncode != 0:
        return _fail("build", r.returncode)

    # --- stage 3: dry-run (validation, fail-closed) ------------------------ #
    print(f"[weekly-qiita-draft] dry-run {draft}")
    r = _run([py, str(POSTER), "dry-run", str(draft)], capture=True)
    print(r.stdout.rstrip())
    if r.returncode != 0 or _DRY_RUN_OK not in r.stdout:
        # Keep the draft on disk so a human can inspect and fix it.
        return _fail("dry-run", r.returncode or 3,
                     "draft kept at " + str(draft) + " — NOT publish-ready")

    print(f"[weekly-qiita-draft] OK — draft is registration-safe: {draft}")
    print("[weekly-qiita-draft] publishing stays a human step: "
          "`py -3.11 " + str(POSTER) + " post " + str(draft) + " --yes`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

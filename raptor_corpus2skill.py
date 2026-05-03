#!/usr/bin/env python3
"""RAPTOR Corpus2Skill - convert a document corpus into a navigable skill hierarchy.

Reads Markdown/text files, RAPTOR findings JSON, CVE/NVD data, and source code
from a source directory, clusters them with TF-IDF + k-means, summarizes each
cluster with claude-haiku, and writes a hierarchical SKILL.md tree under
.claude/skills/corpus/<name>/.

Usage:
    python3 raptor_corpus2skill.py --source /path/to/docs --name my_corpus
    python3 raptor.py corpus2skill --source /path/to/docs --name my_corpus
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.logging import get_logger
from core.run import complete_run, fail_run, get_output_dir, start_run

_RAPTOR_ROOT = Path(__file__).parent


def _load_raptor_env() -> None:
    """Load .claude/raptor.env into os.environ (simple KEY=VALUE parser)."""
    env_file = _RAPTOR_ROOT / ".claude" / "raptor.env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_raptor_env()

logger = get_logger()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="RAPTOR Corpus2Skill - corpus to navigable skill hierarchy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--source", required=True, metavar="PATH",
                   help="Source directory containing documents to ingest")
    p.add_argument("--name", default=None, metavar="NAME",
                   help="Corpus name (default: basename of --source)")
    p.add_argument("--max-depth", type=int, default=2, metavar="N",
                   help="Maximum hierarchy depth (default: 2)")
    p.add_argument("--min-cluster-size", type=int, default=3, metavar="N",
                   help="Minimum documents per cluster (default: 3)")
    p.add_argument("--max-clusters", type=int, default=8, metavar="N",
                   help="Maximum clusters per hierarchy level (default: 8)")
    p.add_argument("--model", default="claude-haiku-4-5-20251001", metavar="MODEL",
                   help="LLM model for summarization (default: claude-haiku-4-5-20251001)")
    p.add_argument("--overwrite", action="store_true",
                   help="Overwrite existing skill directory if present")
    p.add_argument("--resume-summaries", action="store_true",
                   help="Keep existing summaries and only generate missing ones")
    p.add_argument("--out", default=None, metavar="DIR",
                   help="Output directory for the run report (default: auto)")
    return p


def main() -> int:
    args = build_parser().parse_args()
    source = Path(args.source).resolve()

    if not source.exists():
        logger.error("source directory not found: %s", source)
        return 1

    corpus_name = args.name or source.name

    # Resolve run output directory
    try:
        out_dir = get_output_dir("corpus2skill", target_path=str(source),
                                  explicit_out=args.out)
    except Exception as e:
        logger.error("output dir error: %s", e)
        return 1

    start_run(out_dir, "corpus2skill", target=str(source))
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        rc = _run(source, corpus_name, out_dir, args)
    except Exception as e:
        logger.error(f"Corpus2Skill failed: {e}")
        fail_run(out_dir, error=str(e))
        return 1

    if rc == 0:
        complete_run(out_dir)
    else:
        fail_run(out_dir, error=f"exit code {rc}")
    return rc


def _run(source: Path, corpus_name: str, out_dir: Path, args: argparse.Namespace) -> int:
    from core.json import save_json
    from packages.corpus2skill.config import Corpus2SkillConfig
    from packages.corpus2skill.runner import run_corpus2skill

    config = Corpus2SkillConfig(
        source_dir=source,
        output_name=corpus_name,
        max_depth=args.max_depth,
        min_cluster_size=args.min_cluster_size,
        max_clusters_per_level=args.max_clusters,
        model=args.model,
        overwrite=args.overwrite,
        resume_summaries=args.resume_summaries,
    )

    # Warn if output already exists (resume mode may write into an existing dir)
    if config.skills_output_dir.exists() and not args.overwrite and not args.resume_summaries:
        logger.error(
            f"Skill directory already exists: {config.skills_output_dir}"
            "  (use --overwrite to replace, or --resume-summaries to add missing ones)"
        )
        return 1

    t0 = time.monotonic()
    result = run_corpus2skill(config)
    elapsed = time.monotonic() - t0

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": str(source),
        "corpus_name": corpus_name,
        "elapsed_seconds": round(elapsed, 1),
        **result,
    }
    report_path = out_dir / "corpus2skill_report.json"
    save_json(report_path, report)
    print(f"\nRun report: {report_path}")

    return 0 if result.get("status") in ("ok", "empty") else 1


if __name__ == "__main__":
    sys.exit(main())

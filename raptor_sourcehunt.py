#!/usr/bin/env python3
"""
RAPTOR SourceHunt — Clearwing-inspired per-file vulnerability hunting.

Runs a full attack-surface ranking + tiered LLM hunter pipeline against
a source repository, with optional ASan/UBSan crash verification.

Pipeline:
  0. Inventory all source files
  1. Tag each file (memory_unsafe, parser, crypto, auth_boundary,
     syscall_entry, fuzzable)
  2. Rank by attack surface (surface×0.5 + influence×0.2 + reachability×0.3)
  3. Assign tiers A/B/C (35/30/35 % of files; 70/25/5 % of budget)
  4. Hunt in parallel — specialist LLM prompt per file class
  5. ASan/UBSan crash-oracle verification (upgrades evidence level)
  6. Output findings_pool.json + sourcehunt_report.json

Usage:
    raptor sourcehunt --repo /path/to/target
    raptor sourcehunt --repo /path/to/target --depth deep --sanitizer
    raptor sourcehunt --repo /path/to/target --budget 10 --parallel 8
"""

import argparse
import os
import sys
from pathlib import Path

# Path setup — consistent with other raptor_*.py launchers
sys.path.insert(0, str(Path(__file__).parent))

from core.config import RaptorConfig
from core.logging import get_logger
from core.run import get_output_dir, start_run, complete_run, fail_run

logger = get_logger()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="raptor sourcehunt",
        description="Per-file vulnerability hunting with attack-surface ranking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--repo", required=True,
        help="Path to the target repository or source directory",
    )
    p.add_argument(
        "--depth", choices=["quick", "standard", "deep"], default="standard",
        help=(
            "Hunt depth: quick=fast-band only, standard=A:standard/B:fast, "
            "deep=A:deep/B:standard (enables sanitizer by default)"
        ),
    )
    p.add_argument(
        "--budget", type=float, default=5.0, metavar="USD",
        help="Total LLM cost budget in USD (default: 5.0)",
    )
    p.add_argument(
        "--parallel", type=int, default=4, metavar="N",
        help="Max concurrent file hunters (default: 4)",
    )
    p.add_argument(
        "--sanitizer", action="store_true",
        help="Enable ASan/UBSan crash-oracle verification (auto-enabled with --depth deep)",
    )
    p.add_argument(
        "--no-sanitizer", action="store_true",
        help="Disable ASan/UBSan even with --depth deep",
    )
    p.add_argument(
        "--max-files", type=int, default=0, metavar="N",
        help="Limit files to hunt (0 = all, default: 0)",
    )
    p.add_argument(
        "--sarif", metavar="FILE",
        help="Path to existing SARIF file to extract Semgrep hints from",
    )
    p.add_argument(
        "--out", metavar="DIR",
        help="Override output directory",
    )
    p.add_argument(
        "--no-promotion", action="store_true",
        help="Disable deep-band promotion for crash-neighbour files",
    )
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    if not repo_path.exists():
        print(f"Error: Repository path does not exist: {repo_path}", file=sys.stderr)
        return 1

    # Resolve output directory
    out_dir = get_output_dir(
        "sourcehunt",
        target_name=repo_path.name,
        explicit_out=args.out,
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    # Run lifecycle
    try:
        start_run(out_dir, "sourcehunt", target=str(repo_path))
    except Exception as e:
        logger.debug(f"Run metadata: {e}")

    # Sanitizer: enabled if --sanitizer OR depth==deep AND NOT --no-sanitizer
    use_sanitizer = (args.sanitizer or args.depth == "deep") and not args.no_sanitizer

    print("\n" + "=" * 60)
    print("RAPTOR SOURCEHUNT")
    print("=" * 60)
    print(f"  Target: {repo_path}")
    print(f"  Depth:  {args.depth}")
    print(f"  Budget: ${args.budget:.2f}")
    print(f"  Parallel agents: {args.parallel}")
    print(f"  Sanitizer: {'enabled' if use_sanitizer else 'disabled'}")
    if args.sarif:
        print(f"  Semgrep hints: {args.sarif}")
    print()

    try:
        from packages.sourcehunt import run_sourcehunt, SourceHuntConfig

        cfg = SourceHuntConfig(
            repo_path=str(repo_path),
            output_dir=str(out_dir),
            depth=args.depth,
            max_parallel=args.parallel,
            budget_usd=args.budget,
            use_sanitizer=use_sanitizer,
            enable_promotion=not args.no_promotion,
            max_files=args.max_files,
            sarif_path=args.sarif,
        )

        result = run_sourcehunt(cfg)

        print(f"\nReport: {result.report_path}")
        print(f"Findings pool: {out_dir}/findings_pool.json")

        complete_run(out_dir)
        return 0

    except KeyboardInterrupt:
        print("\n[!] Interrupted")
        fail_run(out_dir, error="interrupted")
        return 130
    except Exception as e:
        logger.error(f"SourceHunt failed: {e}", exc_info=True)
        print(f"\nError: {e}", file=sys.stderr)
        fail_run(out_dir, error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())

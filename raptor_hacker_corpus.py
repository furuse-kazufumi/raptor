#!/usr/bin/env python3
"""
RAPTOR Hacker Corpus Fetcher

Fetches data from hacker community sources and saves them to a directory
that corpus2skill can ingest to build a navigable skill hierarchy.

Sources:
  phrack       - Phrack magazine (phrack.org/archives)
  ghsa         - GitHub Security Advisories (GraphQL API)
  capec        - MITRE CAPEC attack patterns (XML)
  d3fend       - MITRE D3FEND defensive techniques (JSON)
  oss_security - OSS-Security mailing list (openwall.com, last 3 years)
  project_zero - Google Project Zero blog (Atom feed)

Usage:
    python3 raptor_hacker_corpus.py [options]

Examples:
    # Fetch all sources
    python3 raptor_hacker_corpus.py

    # Fetch specific sources only
    python3 raptor_hacker_corpus.py --sources phrack,capec

    # Custom output directory, run in parallel
    python3 raptor_hacker_corpus.py --out /tmp/corpus --parallel

    # Force re-download (overwrite cached files)
    python3 raptor_hacker_corpus.py --force
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Ensure stdout/stderr use UTF-8 on Windows so help text renders correctly
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

# ---- Path bootstrap -------------------------------------------------------
# raptor_hacker_corpus.py lives at the RAPTOR root.  Add RAPTOR_DIR to sys.path
# so "packages.*" imports resolve correctly, matching the convention used by
# raptor_sourcehunt.py, raptor_sca.py, etc.
try:
    _RAPTOR_DIR = os.environ["RAPTOR_DIR"]
except KeyError:
    _RAPTOR_DIR = str(Path(__file__).resolve().parent)
if _RAPTOR_DIR not in sys.path:
    sys.path.insert(0, _RAPTOR_DIR)
# ---------------------------------------------------------------------------

from packages.hacker_corpus import ALL_FETCHERS, FetchResult

_DEFAULT_OUT = Path("C:/dev/docs/hacker_corpus")
_ALL_SOURCE_NAMES = sorted(ALL_FETCHERS.keys())


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch hacker community data for corpus2skill ingestion.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""\
Available sources:
  {", ".join(_ALL_SOURCE_NAMES)}

After fetching, build the skill hierarchy with:
  python3 raptor.py corpus2skill --source {_DEFAULT_OUT} --name hacker_corpus
""",
    )
    parser.add_argument(
        "--sources",
        default=",".join(_ALL_SOURCE_NAMES),
        help=(
            f"Comma-separated list of sources to fetch "
            f"(default: all: {', '.join(_ALL_SOURCE_NAMES)})"
        ),
    )
    parser.add_argument(
        "--out",
        default=str(_DEFAULT_OUT),
        help=f"Output directory (default: {_DEFAULT_OUT})",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        default=False,
        help="Run fetchers in parallel (default: sequential)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Re-download files that already exist",
    )
    return parser.parse_args(argv)


def _run_fetcher(name: str, out_dir: Path, force: bool) -> FetchResult:
    fetcher_cls = ALL_FETCHERS[name]
    fetcher = fetcher_cls(output_dir=out_dir, force=force)
    print(f"[*] Starting: {name}")
    t0 = time.monotonic()
    result = fetcher.fetch()
    elapsed = time.monotonic() - t0
    status = str(result)
    print(f"    {status}  ({elapsed:.1f}s)")
    return result


def _print_summary(results: list[FetchResult], elapsed: float) -> None:
    print("\n" + "=" * 60)
    print("Hacker Corpus Fetch Summary")
    print("=" * 60)
    total_fetched = 0
    total_skipped = 0
    total_errors = 0

    for r in results:
        total_fetched += r.count
        total_skipped += r.skipped
        total_errors += len(r.errors)
        err_str = f"  ({len(r.errors)} errors)" if r.errors else ""
        print(f"  {r.source:<16}  fetched={r.count}  skipped={r.skipped}{err_str}")
        for err in r.errors[:3]:
            print(f"               ! {err[:100]}")
        if len(r.errors) > 3:
            print(f"               ... and {len(r.errors) - 3} more errors")

    print("-" * 60)
    print(
        f"  TOTAL  fetched={total_fetched}  skipped={total_skipped}"
        f"  errors={total_errors}  time={elapsed:.1f}s"
    )
    print("=" * 60)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    # Validate source names
    requested = [s.strip() for s in args.sources.split(",") if s.strip()]
    unknown = [s for s in requested if s not in ALL_FETCHERS]
    if unknown:
        print(
            f"Unknown source(s): {', '.join(unknown)}\n"
            f"Available: {', '.join(_ALL_SOURCE_NAMES)}",
            file=sys.stderr,
        )
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {out_dir.resolve()}")
    print(f"Sources: {', '.join(requested)}")
    print(f"Mode: {'parallel' if args.parallel else 'sequential'}")
    print()

    t_start = time.monotonic()
    results: list[FetchResult] = []

    if args.parallel and len(requested) > 1:
        with ThreadPoolExecutor(max_workers=min(len(requested), 4)) as executor:
            futures = {
                executor.submit(_run_fetcher, name, out_dir, args.force): name
                for name in requested
            }
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    name = futures[future]
                    results.append(
                        FetchResult(source=name, errors=[f"Unhandled exception: {exc}"])
                    )
    else:
        for name in requested:
            try:
                results.append(_run_fetcher(name, out_dir, args.force))
            except Exception as exc:
                results.append(
                    FetchResult(source=name, errors=[f"Unhandled exception: {exc}"])
                )

    elapsed = time.monotonic() - t_start
    _print_summary(results, elapsed)

    any_errors = any(r.errors for r in results)
    return 1 if any_errors else 0


if __name__ == "__main__":
    sys.exit(main())

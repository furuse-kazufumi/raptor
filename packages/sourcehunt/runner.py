"""
SourceHunt pipeline runner.

Orchestrates the full pipeline:
  0. Inventory + tagging
  1. Attack-surface ranking
  2. Semgrep hint extraction
  3. Tiered hunter pool (A/B/C)
  4. ASan/UBSan verification pass (optional)
  5. Output: findings_pool.json + sourcehunt_report.json

Mirrors Clearwing's SourceHuntRunner but uses RAPTOR's
existing LLMClient, inventory, and run-lifecycle infrastructure.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.config import RaptorConfig
from core.inventory import build_inventory
from core.logging import get_logger
from core.json import save_json

from .ranker import rank_files, FileScore
from .tagger import tag_files_batch
from .hunter_pool import HunterPool, HunterPoolConfig
from .findings_pool import FindingsPool, PooledFinding, EVIDENCE_LEVELS
from .sanitizer_runner import SanitizerRunner

logger = get_logger()


@dataclass
class SourceHuntConfig:
    """Full pipeline configuration."""

    # Required
    repo_path: str
    output_dir: str

    # Hunt parameters
    depth: str = "standard"          # quick | standard | deep
    max_parallel: int = 4
    budget_usd: float = 5.0

    # Tier band overrides (defaults derived from depth)
    band_a: Optional[str] = None
    band_b: Optional[str] = None
    band_c: Optional[str] = None

    # Features
    use_sanitizer: bool = True
    enable_promotion: bool = True

    # File limits (0 = unlimited)
    max_files: int = 0

    # Optional: pre-built SARIF file to extract Semgrep hints from
    sarif_path: Optional[str] = None

    # LLM config override
    llm_config: Any = None

    def __post_init__(self) -> None:
        # Derive band defaults from depth
        depth_bands = {
            "quick":    ("fast",     "fast",     "fast"),
            "standard": ("standard", "fast",     "fast"),
            "deep":     ("deep",     "standard", "fast"),
        }
        a, b, c = depth_bands.get(self.depth, ("standard", "fast", "fast"))
        if self.band_a is None:
            self.band_a = a
        if self.band_b is None:
            self.band_b = b
        if self.band_c is None:
            self.band_c = c


@dataclass
class SourceHuntResult:
    """Summary of a completed sourcehunt run."""

    repo_path: str
    output_dir: str
    duration_s: float
    files_ranked: int
    files_hunted: int
    total_findings: int
    findings_by_severity: Dict[str, int]
    findings_by_evidence: Dict[str, int]
    crash_confirmed: int
    cost_usd: float
    report_path: str


# ---------------------------------------------------------------------------
# Semgrep hint extraction
# ---------------------------------------------------------------------------

def _extract_semgrep_hints(sarif_path: str) -> Dict[str, str]:
    """Return {relative_file_path: hint_text} from a SARIF file."""
    hints: Dict[str, str] = {}
    try:
        with open(sarif_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return hints

    for run in data.get("runs", []):
        for result in run.get("results", []):
            msg = result.get("message", {}).get("text", "")
            rule_id = result.get("ruleId", "")
            for loc in result.get("locations", []):
                uri = (
                    loc.get("physicalLocation", {})
                       .get("artifactLocation", {})
                       .get("uri", "")
                )
                line = (
                    loc.get("physicalLocation", {})
                       .get("region", {})
                       .get("startLine", 0)
                )
                if uri:
                    hint_line = f"[{rule_id}] line {line}: {msg}"
                    if uri in hints:
                        hints[uri] += "\n" + hint_line
                    else:
                        hints[uri] = hint_line

    return hints


# ---------------------------------------------------------------------------
# Inventory → ranked file list
# ---------------------------------------------------------------------------

def _collect_source_files(repo_path: str, output_dir: str, max_files: int) -> List[str]:
    """Build inventory and return absolute file paths."""
    inventory = build_inventory(repo_path, output_dir)
    files = [
        str(Path(repo_path) / f["path"])
        for f in inventory.get("files", [])
        if not f.get("generated")
    ]
    if max_files and len(files) > max_files:
        files = files[:max_files]
    return files


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_sourcehunt(config: SourceHuntConfig) -> SourceHuntResult:
    """Execute the full sourcehunt pipeline synchronously.

    Returns a SourceHuntResult summary; detailed findings are written to
    output_dir/findings_pool.json and output_dir/sourcehunt_report.json.
    """
    start = time.monotonic()
    out = Path(config.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    repo_path = str(Path(config.repo_path).resolve())

    # ------------------------------------------------------------------
    # Step 0: Inventory
    # ------------------------------------------------------------------
    print("\n[sourcehunt] Building inventory...")
    files = _collect_source_files(repo_path, str(out), config.max_files)
    logger.info(f"[sourcehunt] {len(files)} source files found")

    if not files:
        logger.warning("[sourcehunt] No source files found — aborting")
        return _empty_result(config, start)

    # ------------------------------------------------------------------
    # Step 1: Rank
    # ------------------------------------------------------------------
    print(f"[sourcehunt] Ranking {len(files)} files by attack surface...")
    ranked = rank_files(files, repo_root=repo_path)

    # Print tier distribution
    tier_counts = {"A": 0, "B": 0, "C": 0}
    for fs in ranked:
        tier_counts[fs.tier] = tier_counts.get(fs.tier, 0) + 1
    print(
        f"[sourcehunt] Tiers — A: {tier_counts['A']} files, "
        f"B: {tier_counts['B']}, C: {tier_counts['C']}"
    )

    # Save ranking to disk
    save_json(out / "file_rankings.json", [fs.to_dict() for fs in ranked])

    # Show top-10
    print("\n[sourcehunt] Top 10 attack-surface files:")
    for fs in ranked[:10]:
        tags_str = ",".join(sorted(fs.tags)) or "—"
        print(
            f"  [{fs.tier}] {Path(fs.file).name:<45} "
            f"score={fs.score:.3f}  tags=[{tags_str}]"
        )

    # ------------------------------------------------------------------
    # Step 2: Semgrep hints
    # ------------------------------------------------------------------
    semgrep_hints: Dict[str, str] = {}
    if config.sarif_path and Path(config.sarif_path).exists():
        semgrep_hints = _extract_semgrep_hints(config.sarif_path)
        print(f"[sourcehunt] Loaded {len(semgrep_hints)} Semgrep hints")

    # ------------------------------------------------------------------
    # Step 2b: Knowledge base hints
    # ------------------------------------------------------------------
    corpus_kb = None
    try:
        from packages.hacker_corpus.knowledge_base import KnowledgeBase
        corpus_kb = KnowledgeBase.auto_discover()
        if corpus_kb:
            print("[sourcehunt] Corpus knowledge base loaded")
    except Exception:
        pass  # knowledge base is optional

    # ------------------------------------------------------------------
    # Step 3: Hunter pool
    # ------------------------------------------------------------------
    pool_config = HunterPoolConfig(
        ranked_files=ranked,
        repo_root=repo_path,
        output_dir=str(out),
        budget_usd=config.budget_usd,
        max_parallel=config.max_parallel,
        band_a=config.band_a or "standard",
        band_b=config.band_b or "fast",
        band_c=config.band_c or "fast",
        use_sanitizer=config.use_sanitizer,
        semgrep_hints=semgrep_hints,
        enable_promotion=config.enable_promotion,
        llm_config=config.llm_config,
        corpus_kb=corpus_kb,
    )

    print(f"\n[sourcehunt] Starting hunt (depth={config.depth}, "
          f"max_parallel={config.max_parallel}, budget=${config.budget_usd})...")

    pool = HunterPool(pool_config)
    hunt_results = asyncio.run(pool.run())

    # ------------------------------------------------------------------
    # Step 4: Optional full sanitizer pass over static_corroboration findings
    # ------------------------------------------------------------------
    if config.use_sanitizer and config.depth == "deep":
        _run_sanitizer_pass(pool.findings_pool, str(out))

    # ------------------------------------------------------------------
    # Step 5: Report
    # ------------------------------------------------------------------
    all_findings = pool.all_findings()
    cost = sum(r.cost_usd for r in hunt_results)
    duration = time.monotonic() - start

    by_sev: Dict[str, int] = {}
    by_ev: Dict[str, int] = {}
    for f in all_findings:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
        by_ev[f.evidence_level] = by_ev.get(f.evidence_level, 0) + 1

    crash_confirmed = sum(
        1 for f in all_findings if f.evidence_level == "crash_reproduced"
    )

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repo": repo_path,
        "depth": config.depth,
        "duration_seconds": round(duration, 1),
        "files_ranked": len(ranked),
        "files_hunted": len(hunt_results),
        "total_findings": len(all_findings),
        "crash_confirmed": crash_confirmed,
        "cost_usd": round(cost, 4),
        "tier_costs": pool.cost_summary(),
        "findings_by_severity": by_sev,
        "findings_by_evidence": by_ev,
        "findings": [f.to_dict() for f in all_findings],
    }
    report_path = out / "sourcehunt_report.json"
    save_json(report_path, report)

    _print_summary(all_findings, by_sev, by_ev, crash_confirmed, cost, duration)

    return SourceHuntResult(
        repo_path=repo_path,
        output_dir=str(out),
        duration_s=duration,
        files_ranked=len(ranked),
        files_hunted=len(hunt_results),
        total_findings=len(all_findings),
        findings_by_severity=by_sev,
        findings_by_evidence=by_ev,
        crash_confirmed=crash_confirmed,
        cost_usd=cost,
        report_path=str(report_path),
    )


def _run_sanitizer_pass(pool: FindingsPool, output_dir: str) -> None:
    """Run sanitizer on all static_corroboration findings that have a compile cmd."""
    candidates = [
        f for f in pool.get_above_evidence("static_corroboration")
        if f.evidence_level == "static_corroboration" and f.sanitizer_cmd
    ]
    if not candidates:
        return

    runner = SanitizerRunner()
    if not runner.available:
        logger.info("[sourcehunt] Sanitizer not available — skipping verification pass")
        return

    print(f"\n[sourcehunt] Sanitizer verification pass: {len(candidates)} candidates")

    for f in candidates:
        ev = runner.verify_with_generated_input(
            source_file=f.file,
            function_name="",
        )
        if ev.crashed:
            pool.upgrade_evidence(
                f.finding_id, "crash_reproduced", crash_output=ev.raw_output
            )
            print(f"  [!] CRASH confirmed: {f.title} ({ev.error_type})")
        else:
            logger.debug(f"[sanitizer] No crash: {f.title}")


def _print_summary(
    findings: List[PooledFinding],
    by_sev: Dict[str, int],
    by_ev: Dict[str, int],
    crash_confirmed: int,
    cost: float,
    duration: float,
) -> None:
    print("\n" + "=" * 60)
    print("SOURCEHUNT COMPLETE")
    print("=" * 60)
    print(f"  Total findings:   {len(findings)}")
    for sev in ("critical", "high", "medium", "low"):
        n = by_sev.get(sev, 0)
        if n:
            print(f"    {sev:<10} {n}")
    print(f"  Crash confirmed:  {crash_confirmed}")
    print(f"  Evidence ladder:")
    for lvl in EVIDENCE_LEVELS:
        n = by_ev.get(lvl, 0)
        if n:
            print(f"    {lvl:<25} {n}")
    print(f"  Cost:  ${cost:.4f}")
    print(f"  Time:  {duration:.0f}s")
    print("=" * 60)


def _empty_result(config: SourceHuntConfig, start: float) -> SourceHuntResult:
    return SourceHuntResult(
        repo_path=config.repo_path,
        output_dir=config.output_dir,
        duration_s=time.monotonic() - start,
        files_ranked=0, files_hunted=0, total_findings=0,
        findings_by_severity={}, findings_by_evidence={},
        crash_confirmed=0, cost_usd=0.0,
        report_path="",
    )

"""
Tiered hunter pool — parallel per-file vulnerability hunting.

Budget allocation mirrors Clearwing (70 / 25 / 5):
  Tier A files – 70 % of total hunt budget
  Tier B files – 25 %
  Tier C files  –  5 %  (quick-pass only)

Band system:
  fast      – constrained prompt, 20-step limit
  standard  – full specialist prompt
  deep      – full prompt + sanitizer verification

A finding with evidence_level >= crash_reproduced from a lower-tier file
triggers promotion of neighbouring files (same directory) to Tier B.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.logging import get_logger
from .ranker import FileScore
from .findings_pool import FindingsPool, PooledFinding, evidence_at_or_above
from .specialist_prompts import build_hunt_prompt, select_specialist
from .sanitizer_runner import SanitizerRunner

logger = get_logger()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TIER_BUDGET_FRACTION = {"A": 0.70, "B": 0.25, "C": 0.05}

# Maximum files hunted per tier when no explicit budget is set
TIER_MAX_FILES = {"A": 999, "B": 50, "C": 20}

# Content truncation per band to control token use
BAND_CONTENT_LIMIT = {"fast": 8_000, "standard": 20_000, "deep": 40_000}

# Max LLM steps per file per band
BAND_MAX_STEPS = {"fast": 1, "standard": 1, "deep": 2}

_FINDING_ID_RE = re.compile(r"[^a-zA-Z0-9_-]")


def _make_finding_id(file: str, line: int, title: str) -> str:
    slug = _FINDING_ID_RE.sub("_", f"{Path(file).stem}_{line}_{title[:20]}")
    return slug.lower()


@dataclass
class HunterPoolConfig:
    """Configuration for a HunterPool run."""

    ranked_files: List[FileScore]
    repo_root: str
    output_dir: str

    # Budget
    budget_usd: float = 5.0          # total LLM budget
    max_parallel: int = 4            # concurrent file hunters

    # Band for each tier
    band_a: str = "standard"
    band_b: str = "fast"
    band_c: str = "fast"

    # Enable sanitizer verification for crash_reproduced evidence
    use_sanitizer: bool = True

    # Optional Semgrep SARIF findings keyed by relative file path
    semgrep_hints: Dict[str, str] = field(default_factory=dict)

    # Starting band: promoted files get "deep"
    enable_promotion: bool = True

    # LLM config override (None = use env defaults)
    llm_config: Any = None

    # Optional KnowledgeBase instance for corpus-informed prompts
    corpus_kb: Any = None   # packages.hacker_corpus.knowledge_base.KnowledgeBase


@dataclass
class HuntResult:
    """Per-file hunt outcome."""

    file: str
    tier: str
    band: str
    findings: List[PooledFinding]
    cost_usd: float
    duration_s: float
    error: str = ""


# ---------------------------------------------------------------------------
# Per-file hunter
# ---------------------------------------------------------------------------

class _FileHunter:
    """Single-file vulnerability hunter using a specialist LLM prompt."""

    def __init__(
        self,
        file_score: FileScore,
        config: HunterPoolConfig,
        findings_pool: FindingsPool,
        llm_client: Any,
        band: str,
    ):
        self._fs = file_score
        self._cfg = config
        self._pool = findings_pool
        self._llm = llm_client
        self._band = band

    async def hunt(self) -> HuntResult:
        start = time.monotonic()
        path = self._fs.path

        try:
            content = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return HuntResult(
                file=path, tier=self._fs.tier, band=self._band,
                findings=[], cost_usd=0.0,
                duration_s=time.monotonic() - start,
                error=str(e),
            )

        limit = BAND_CONTENT_LIMIT[self._band]
        truncated = content[:limit]

        rel_path = path
        try:
            rel_path = str(Path(path).relative_to(self._cfg.repo_root))
        except ValueError:
            pass

        semgrep_hint = self._cfg.semgrep_hints.get(rel_path, "")

        corpus_hints = ""
        if self._cfg.corpus_kb is not None:
            try:
                corpus_hints = self._cfg.corpus_kb.get_hints_for_set(self._fs.tags)
            except Exception:
                pass  # corpus hints are optional

        system_prompt, user_prompt = build_hunt_prompt(
            file_path=rel_path,
            content=truncated,
            tags=self._fs.tags,
            semgrep_hints=semgrep_hint or None,
            corpus_hints=corpus_hints,
        )

        # LLM call (synchronous, wrapped for async)
        findings: List[PooledFinding] = []
        cost = 0.0
        try:
            response = await asyncio.to_thread(
                self._llm.generate,
                prompt=user_prompt,
                system_prompt=system_prompt,
                task_type="analysis",
            )
            cost = getattr(response, "cost", 0.0) or 0.0
            findings = _parse_llm_findings(response.content or "", path, self._fs.tags)
        except Exception as e:
            logger.warning(f"[hunter] LLM call failed for {path}: {e}")
            return HuntResult(
                file=path, tier=self._fs.tier, band=self._band,
                findings=[], cost_usd=cost,
                duration_s=time.monotonic() - start,
                error=str(e),
            )

        # Deep band: run sanitizer on promising findings
        if self._band == "deep" and self._cfg.use_sanitizer:
            runner = SanitizerRunner()
            if runner.available:
                for f in findings:
                    if f.sanitizer_cmd and evidence_at_or_above(
                        f.evidence_level, "static_corroboration"
                    ):
                        ev = await asyncio.to_thread(
                            runner.verify_with_generated_input,
                            source_file=path,
                            function_name="",
                        )
                        if ev.crashed:
                            self._pool.upgrade_evidence(
                                f.finding_id,
                                "crash_reproduced",
                                crash_output=ev.raw_output,
                            )
                            f.evidence_level = "crash_reproduced"
                            f.crash_output = ev.raw_output

        for f in findings:
            self._pool.add(f)

        return HuntResult(
            file=path,
            tier=self._fs.tier,
            band=self._band,
            findings=findings,
            cost_usd=cost,
            duration_s=time.monotonic() - start,
        )


# ---------------------------------------------------------------------------
# JSON findings parser
# ---------------------------------------------------------------------------

def _parse_llm_findings(
    content: str,
    file_path: str,
    tags: set[str],
) -> List[PooledFinding]:
    """Extract PooledFinding list from LLM JSON response."""
    # Strip markdown fences if present
    content = re.sub(r"```(?:json)?\s*", "", content).replace("```", "").strip()

    # Find first JSON object
    start = content.find("{")
    if start == -1:
        return []

    try:
        data = json.loads(content[start:])
    except json.JSONDecodeError:
        # Try to extract partial JSON
        end = content.rfind("}")
        if end == -1:
            return []
        try:
            data = json.loads(content[start:end + 1])
        except json.JSONDecodeError:
            return []

    raw_findings = data.get("findings", [])
    result: List[PooledFinding] = []

    for raw in raw_findings:
        if not isinstance(raw, dict):
            continue
        title = raw.get("title", "Untitled finding")
        line_start = int(raw.get("line_start", 0) or 0)
        fid = _make_finding_id(file_path, line_start, title)

        result.append(PooledFinding(
            finding_id=fid,
            file=file_path,
            line_start=line_start,
            line_end=int(raw.get("line_end", line_start) or line_start),
            title=title,
            cwe=raw.get("cwe", "CWE-0"),
            severity=raw.get("severity", "medium"),
            evidence_level=raw.get("evidence_level", "suspicion"),
            description=raw.get("description", ""),
            trigger_input=raw.get("trigger_input", ""),
            sanitizer_cmd=raw.get("sanitizer_cmd", ""),
            tags=sorted(tags),
        ))

    return result


# ---------------------------------------------------------------------------
# Pool orchestrator
# ---------------------------------------------------------------------------

class HunterPool:
    """Orchestrate tiered parallel file hunting.

    Usage:
        pool = HunterPool(config)
        results = asyncio.run(pool.run())
    """

    def __init__(self, config: HunterPoolConfig):
        self._cfg = config
        self._pool = FindingsPool(
            checkpoint_path=str(Path(config.output_dir) / "findings_pool.json")
        )
        self._spent: Dict[str, float] = {"A": 0.0, "B": 0.0, "C": 0.0}
        self._results: List[HuntResult] = []

    # ------------------------------------------------------------------
    # Budget helpers
    # ------------------------------------------------------------------

    def _tier_budget(self, tier: str) -> float:
        return self._cfg.budget_usd * TIER_BUDGET_FRACTION.get(tier, 0.05)

    def _band_for_tier(self, tier: str) -> str:
        return {
            "A": self._cfg.band_a,
            "B": self._cfg.band_b,
            "C": self._cfg.band_c,
        }.get(tier, "fast")

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    async def run(self) -> List[HuntResult]:
        """Run the tiered hunt and return all per-file results."""
        from packages.llm_analysis import get_client, LLMConfig
        cfg = self._cfg.llm_config or LLMConfig(
            max_cost_per_scan=self._cfg.budget_usd
        )
        llm = get_client(cfg)
        if llm is None:
            logger.warning("[hunter_pool] No LLM available — skipping hunt")
            return []

        semaphore = asyncio.Semaphore(self._cfg.max_parallel)

        # Group files by tier
        tiers: Dict[str, List[FileScore]] = {"A": [], "B": [], "C": []}
        for fs in self._cfg.ranked_files:
            tiers.setdefault(fs.tier, []).append(fs)

        # Process tiers A → B → C sequentially (findings from A inform B)
        for tier in ("A", "B", "C"):
            files = tiers.get(tier, [])
            if not files:
                continue

            budget_left = self._tier_budget(tier)
            band = self._band_for_tier(tier)

            logger.info(
                f"[hunter_pool] Tier {tier}: {len(files)} files, "
                f"budget=${budget_left:.2f}, band={band}"
            )
            print(
                f"\n[sourcehunt] Tier {tier} — {len(files)} files "
                f"(budget ${budget_left:.2f}, {band} band)"
            )

            tasks = []
            for fs in files:
                if self._spent[tier] >= budget_left:
                    logger.info(f"[hunter_pool] Tier {tier} budget exhausted")
                    break
                hunter = _FileHunter(
                    file_score=fs,
                    config=self._cfg,
                    findings_pool=self._pool,
                    llm_client=llm,
                    band=band,
                )
                tasks.append(self._bounded_hunt(semaphore, hunter, tier))

            tier_results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in tier_results:
                if isinstance(r, HuntResult):
                    self._results.append(r)
                    self._spent[tier] += r.cost_usd
                elif isinstance(r, Exception):
                    logger.warning(f"[hunter_pool] Hunt task failed: {r}")

            # Promotion: files adjacent to crash-confirmed findings → deep band
            if self._cfg.enable_promotion and tier == "B":
                await self._promote_neighbours(tiers, llm)

        self._pool.save()
        return self._results

    async def _bounded_hunt(
        self,
        sem: asyncio.Semaphore,
        hunter: _FileHunter,
        tier: str,
    ) -> HuntResult:
        async with sem:
            result = await hunter.hunt()
            n = len(result.findings)
            marker = "  [!]" if n > 0 else "  [ ]"
            print(
                f"{marker} {Path(result.file).name:<40} "
                f"tier={tier} findings={n} ${result.cost_usd:.3f}"
            )
            return result

    async def _promote_neighbours(
        self,
        tiers: Dict[str, List[FileScore]],
        llm: Any,
    ) -> None:
        """Re-run C-tier files in the same directory as crash-confirmed findings."""
        crash_dirs = {
            Path(f.file).parent
            for f in self._pool.get_above_evidence("crash_reproduced")
        }
        if not crash_dirs:
            return

        promoted: List[FileScore] = []
        remaining_c: List[FileScore] = []
        for fs in tiers.get("C", []):
            if Path(fs.file).parent in crash_dirs:
                promoted.append(fs)
            else:
                remaining_c.append(fs)

        if not promoted:
            return

        logger.info(f"[hunter_pool] Promoting {len(promoted)} C→deep files near crash sites")
        print(f"\n[sourcehunt] Promoting {len(promoted)} files to deep band (crash neighbour)")

        sem = asyncio.Semaphore(self._cfg.max_parallel)
        tasks = [
            self._bounded_hunt(
                sem,
                _FileHunter(fs, self._cfg, self._pool, llm, "deep"),
                "C*",
            )
            for fs in promoted
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, HuntResult):
                self._results.append(r)

        tiers["C"] = remaining_c

    # ------------------------------------------------------------------
    # Results accessors
    # ------------------------------------------------------------------

    @property
    def findings_pool(self) -> FindingsPool:
        return self._pool

    def cost_summary(self) -> Dict[str, float]:
        return dict(self._spent)

    def all_findings(self) -> List[PooledFinding]:
        return self._pool.all()

"""
Shared findings pool for cross-agent primitive chaining.

Agents write findings here as they discover them; later agents can
query for complementary primitives (e.g. an info-leak that enables a
write-what-where to become a full exploit chain).

Backed by a JSON file for persistence across pool restarts.
Evidence levels follow Clearwing's 6-step ladder:

  suspicion → static_corroboration → crash_reproduced
  → root_cause_explained → exploit_demonstrated → patch_validated
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

# Ordered evidence levels (weakest → strongest)
EVIDENCE_LEVELS = [
    "suspicion",
    "static_corroboration",
    "crash_reproduced",
    "root_cause_explained",
    "exploit_demonstrated",
    "patch_validated",
]

_LEVEL_RANK = {lvl: i for i, lvl in enumerate(EVIDENCE_LEVELS)}


def evidence_at_or_above(level: str, threshold: str) -> bool:
    """Return True when *level* is at least as strong as *threshold*."""
    return _LEVEL_RANK.get(level, 0) >= _LEVEL_RANK.get(threshold, 0)


@dataclass
class PooledFinding:
    """A single vulnerability finding shared across agents."""

    finding_id: str
    file: str
    line_start: int
    line_end: int
    title: str
    cwe: str
    severity: str
    evidence_level: str
    description: str
    trigger_input: str = ""
    sanitizer_cmd: str = ""
    crash_output: str = ""     # populated by SanitizerRunner
    tags: list[str] = field(default_factory=list)
    # primitive type for chaining: info_leak | arbitrary_write | oob_read | ...
    primitive: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PooledFinding":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @property
    def is_high_confidence(self) -> bool:
        return evidence_at_or_above(self.evidence_level, "crash_reproduced")


class FindingsPool:
    """Thread-safe pool of findings shared across parallel hunter agents.

    Usage:
        pool = FindingsPool(checkpoint_path="out/findings_pool.json")
        pool.add(finding)
        leaks = pool.get_by_primitive("info_leak")
    """

    def __init__(self, checkpoint_path: Optional[str] = None):
        self._lock = threading.Lock()
        self._findings: List[PooledFinding] = []
        self._checkpoint = Path(checkpoint_path) if checkpoint_path else None

        if self._checkpoint and self._checkpoint.exists():
            self._load()

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(self, finding: PooledFinding) -> None:
        """Add or upgrade a finding (upgrades if same finding_id exists)."""
        with self._lock:
            for i, existing in enumerate(self._findings):
                if existing.finding_id == finding.finding_id:
                    # Keep the stronger evidence level
                    if (
                        _LEVEL_RANK.get(finding.evidence_level, 0)
                        > _LEVEL_RANK.get(existing.evidence_level, 0)
                    ):
                        self._findings[i] = finding
                    return
            self._findings.append(finding)
            self._save()

    def upgrade_evidence(
        self,
        finding_id: str,
        new_level: str,
        crash_output: str = "",
    ) -> bool:
        """Upgrade an existing finding's evidence level.

        Returns True when the upgrade was applied.
        """
        with self._lock:
            for f in self._findings:
                if f.finding_id == finding_id:
                    if _LEVEL_RANK.get(new_level, 0) > _LEVEL_RANK.get(f.evidence_level, 0):
                        f.evidence_level = new_level
                        if crash_output:
                            f.crash_output = crash_output
                        self._save()
                        return True
                    return False
            return False

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def all(self) -> List[PooledFinding]:
        with self._lock:
            return list(self._findings)

    def get_by_file(self, file_path: str) -> List[PooledFinding]:
        with self._lock:
            return [f for f in self._findings if f.file == file_path]

    def get_by_cwe(self, cwe_prefix: str) -> List[PooledFinding]:
        """e.g. get_by_cwe("CWE-119") returns all CWE-119 variants."""
        with self._lock:
            return [f for f in self._findings if f.cwe.startswith(cwe_prefix)]

    def get_by_primitive(self, primitive: str) -> List[PooledFinding]:
        with self._lock:
            return [f for f in self._findings if f.primitive == primitive]

    def get_by_severity(self, severity: str) -> List[PooledFinding]:
        with self._lock:
            return [f for f in self._findings if f.severity == severity]

    def get_above_evidence(self, threshold: str) -> List[PooledFinding]:
        with self._lock:
            return [
                f for f in self._findings
                if evidence_at_or_above(f.evidence_level, threshold)
            ]

    def chain_candidates(self, primitive_a: str, primitive_b: str) -> list[tuple]:
        """Return (finding_a, finding_b) pairs that could form an exploit chain."""
        with self._lock:
            as_ = [f for f in self._findings if f.primitive == primitive_a]
            bs = [f for f in self._findings if f.primitive == primitive_b]
        return [(a, b) for a in as_ for b in bs if a.file != b.file]

    def summary(self) -> dict:
        with self._lock:
            by_sev: dict[str, int] = {}
            by_evidence: dict[str, int] = {}
            for f in self._findings:
                by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
                by_evidence[f.evidence_level] = by_evidence.get(f.evidence_level, 0) + 1
            return {
                "total": len(self._findings),
                "by_severity": by_sev,
                "by_evidence": by_evidence,
            }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        try:
            data = json.loads(self._checkpoint.read_text(encoding="utf-8"))
            self._findings = [PooledFinding.from_dict(d) for d in data.get("findings", [])]
        except Exception:
            self._findings = []

    def _save(self) -> None:
        if not self._checkpoint:
            return
        try:
            self._checkpoint.parent.mkdir(parents=True, exist_ok=True)
            payload = {"findings": [f.to_dict() for f in self._findings]}
            self._checkpoint.write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def save(self) -> None:
        """Explicit save (call after bulk inserts)."""
        with self._lock:
            self._save()

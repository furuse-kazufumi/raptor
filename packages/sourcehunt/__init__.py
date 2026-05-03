"""
RAPTOR SourceHunt — Clearwing-inspired per-file vulnerability hunting.

Implements:
  - Attack-surface tagging (memory_unsafe, parser, crypto, auth_boundary,
    syscall_entry, fuzzable)
  - Weighted file ranking  (surface×0.5 + influence×0.2 + reachability×0.3)
  - Tiered A/B/C hunter pool (70/25/5 budget split)
  - Specialist-routed LLM prompts (6 classes)
  - ASan/UBSan crash-oracle verification
  - Cross-agent findings pool for primitive chaining

Public API:
    from packages.sourcehunt import run_sourcehunt, SourceHuntConfig
    from packages.sourcehunt import tag_files_batch, rank_files
    from packages.sourcehunt import SanitizerRunner
    from packages.sourcehunt import FindingsPool
"""

from .tagger import tag_file, tag_files_batch
from .ranker import rank_files, FileScore
from .findings_pool import FindingsPool, PooledFinding
from .sanitizer_runner import SanitizerRunner, CrashEvidence
from .hunter_pool import HunterPool, HunterPoolConfig
from .runner import run_sourcehunt, SourceHuntConfig, SourceHuntResult

__all__ = [
    "tag_file",
    "tag_files_batch",
    "rank_files",
    "FileScore",
    "FindingsPool",
    "PooledFinding",
    "SanitizerRunner",
    "CrashEvidence",
    "HunterPool",
    "HunterPoolConfig",
    "run_sourcehunt",
    "SourceHuntConfig",
    "SourceHuntResult",
]

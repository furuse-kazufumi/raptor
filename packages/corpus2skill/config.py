"""Corpus2Skill configuration dataclass."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Corpus2SkillConfig:
    source_dir: Path
    output_name: str
    max_depth: int = 2
    min_cluster_size: int = 3
    max_clusters_per_level: int = 8
    model: str = "claude-haiku-4-5-20251001"
    overwrite: bool = False
    resume_summaries: bool = False
    raptor_dir: Path = field(default=None)

    def __post_init__(self) -> None:
        self.source_dir = Path(self.source_dir).resolve()
        if self.raptor_dir is None:
            self.raptor_dir = Path(__file__).resolve().parents[2]
        else:
            self.raptor_dir = Path(self.raptor_dir).resolve()

    @property
    def skills_output_dir(self) -> Path:
        return self.raptor_dir / ".claude" / "skills" / "corpus" / self.output_name

"""
Base class for hacker corpus fetchers.

Each fetcher downloads data from a specific source and saves it to
a structured directory for corpus2skill ingestion.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class FetchResult:
    """Result of a single fetcher run."""

    source: str
    count: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def total_attempted(self) -> int:
        return self.count + self.skipped + len(self.errors)

    def __str__(self) -> str:
        parts = [f"{self.source}: {self.count} fetched"]
        if self.skipped:
            parts.append(f"{self.skipped} skipped")
        if self.errors:
            parts.append(f"{len(self.errors)} errors")
        return ", ".join(parts)


class CorpusFetcher(ABC):
    """Abstract base class for corpus data fetchers."""

    #: Identifier used in CLI and output paths
    name: str = ""
    #: Seconds to sleep between requests (subclasses may override)
    rate_limit: float = 1.0

    def __init__(self, output_dir: Path, force: bool = False) -> None:
        self.output_dir = Path(output_dir)
        self.force = force

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self) -> FetchResult:
        """Fetch data and save to output_dir. Returns FetchResult."""
        result = FetchResult(source=self.name)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._do_fetch(result)
        return result

    # ------------------------------------------------------------------
    # Subclass contract
    # ------------------------------------------------------------------

    @abstractmethod
    def _do_fetch(self, result: FetchResult) -> None:
        """Subclasses implement fetching logic here, updating result in place."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _should_skip(self, path: Path) -> bool:
        """Return True if the file already exists and --force is not set."""
        return path.exists() and not self.force

    def _sleep(self) -> None:
        """Respect rate limit between requests."""
        time.sleep(self.rate_limit)

    def _safe_write(self, path: Path, content: str) -> None:
        """Write content to path, creating parent directories as needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

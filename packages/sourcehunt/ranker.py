"""
Attack-surface file ranker.

Score formula (mirrors Clearwing):
    score = surface × 0.5 + influence × 0.2 + reachability × 0.3

  surface      – external-facing entry-point density for this file
  influence    – how many other files import / include this one
  reachability – inverse of directory depth from repo root
                 (shallow = more reachable from attackers)

High-value security tags receive a surface bonus so that a small C file
full of memory operations outranks a large but unreachable utility module.

Tier assignment (A/B/C) drives budget allocation in HunterPool:
  A – top  35 % by score  → 70 % of hunt budget
  B – next 30 %           → 25 %
  C – remaining 35 %      →  5 %
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.inventory.languages import detect_language
from .tagger import tag_file

# ---------------------------------------------------------------------------
# Entry-point detection (cross-language)
# ---------------------------------------------------------------------------

_ENTRY_RE = re.compile(
    r"(?:"
    r"^pub\s+(?:unsafe\s+)?fn\s+\w+"                           # Rust
    r"|^extern\s+\"C\"\s*\{"
    r"|^(?:void|int|char\s*\*|bool|size_t|ssize_t|uint\w*|int\w*)\s+"
      r"\w+\s*\([^)]{0,200}\)\s*\{"                            # C
    r"|^\s*(?:public|protected|internal)\s+\w[\w<>\[\]?]*\s+\w+\s*\("  # Java/C#
    r"|^def\s+[a-z]\w*\s*\("                                   # Python
    r"|^(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+\w+"  # JS/TS
    r")",
    re.MULTILINE,
)

# Per-language import / include patterns
_IMPORT_RE: Dict[str, re.Pattern] = {
    "c":          re.compile(r'^\s*#include\s+[<"]([^>"]+)[>"]', re.MULTILINE),
    "cpp":        re.compile(r'^\s*#include\s+[<"]([^>"]+)[>"]', re.MULTILINE),
    "python":     re.compile(
        r'^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))', re.MULTILINE
    ),
    "javascript": re.compile(
        r'(?:require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)|'
        r'from\s+[\'"]([^\'"]+)[\'"])',
        re.MULTILINE,
    ),
    "typescript": re.compile(
        r'(?:require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)|'
        r'from\s+[\'"]([^\'"]+)[\'"])',
        re.MULTILINE,
    ),
    "rust":       re.compile(r'(?:use\s+([\w:]+)|extern\s+crate\s+(\w+))', re.MULTILINE),
    "go":         re.compile(r'"([\w./]+)"', re.MULTILINE),
    "java":       re.compile(r'^\s*import\s+([\w.*]+)', re.MULTILINE),
}

# Security-tag surface bonuses applied before normalisation
_TAG_BONUS: Dict[str, float] = {
    "memory_unsafe": 0.18,
    "syscall_entry": 0.14,
    "parser":        0.08,
    "crypto":        0.06,
    "auth_boundary": 0.06,
    "fuzzable":      0.04,
}


@dataclass
class FileScore:
    """Per-file attack-surface score and metadata."""

    path: str
    surface: float = 0.0
    influence: float = 0.0
    reachability: float = 0.0
    tags: set[str] = field(default_factory=set)
    tier: str = "C"

    @property
    def score(self) -> float:
        return self.surface * 0.5 + self.influence * 0.2 + self.reachability * 0.3

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "score": round(self.score, 4),
            "surface": round(self.surface, 4),
            "influence": round(self.influence, 4),
            "reachability": round(self.reachability, 4),
            "tags": sorted(self.tags),
            "tier": self.tier,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_safe(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _count_entries(content: str) -> int:
    return len(_ENTRY_RE.findall(content))


def _build_influence_map(
    file_contents: Dict[str, str],
    lang_map: Dict[str, str],
) -> Dict[str, int]:
    """Return {file_path: import_count} — how many files include each file."""
    influence: Dict[str, int] = {p: 0 for p in file_contents}
    stem_to_path: Dict[str, str] = {Path(p).stem: p for p in file_contents}

    for path, content in file_contents.items():
        lang = lang_map.get(path, "c")
        pattern = _IMPORT_RE.get(lang)
        if not pattern:
            continue
        for m in pattern.finditer(content):
            imported = next(
                (g for g in m.groups() if g),
                None,
            )
            if not imported:
                continue
            stem = Path(imported.replace(".", "/")).stem
            target = stem_to_path.get(stem)
            if target and target != path:
                influence[target] += 1

    return influence


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rank_files(
    file_paths: List[str],
    repo_root: str,
    tier_split: tuple[float, float, float] = (0.35, 0.30, 0.35),
) -> List[FileScore]:
    """Rank source files by weighted attack-surface score.

    Args:
        file_paths:  Source files to evaluate.
        repo_root:   Repository root directory for depth calculation.
        tier_split:  Fraction of files assigned to A / B / C tiers.
                     Defaults to (0.35, 0.30, 0.35).

    Returns:
        List of FileScore objects sorted by score descending, with
        tier assignments applied.
    """
    if not file_paths:
        return []

    root = Path(repo_root)

    # Load all content and language info once
    contents: Dict[str, str] = {p: _read_safe(p) for p in file_paths}
    lang_map: Dict[str, str] = {
        p: (detect_language(p) or "c") for p in file_paths
    }

    influence_map = _build_influence_map(contents, lang_map)
    max_influence = max(influence_map.values(), default=1) or 1

    max_depth = 1
    for p in file_paths:
        try:
            d = len(Path(p).relative_to(root).parts)
            if d > max_depth:
                max_depth = d
        except ValueError:
            pass

    scores: List[FileScore] = []
    for p in file_paths:
        content = contents[p]
        tags = tag_file(p, content)

        # --- surface ---
        entry_count = _count_entries(content)
        line_count = max(content.count("\n"), 1)
        raw_surface = entry_count / max(line_count / 50, 1)
        tag_bonus = sum(_TAG_BONUS.get(t, 0) for t in tags)
        surface = min(raw_surface + tag_bonus, 1.0)

        # --- influence ---
        influence = influence_map.get(p, 0) / max_influence

        # --- reachability ---
        try:
            depth = len(Path(p).relative_to(root).parts)
            reachability = 1.0 - (depth / max_depth)
        except ValueError:
            reachability = 0.5

        scores.append(FileScore(
            path=p,
            surface=surface,
            influence=influence,
            reachability=reachability,
            tags=tags,
        ))

    scores.sort(key=lambda x: x.score, reverse=True)

    # Assign tiers
    n = len(scores)
    cut_ab = int(n * tier_split[0])
    cut_bc = cut_ab + int(n * tier_split[1])

    for i, fs in enumerate(scores):
        if i < cut_ab:
            fs.tier = "A"
        elif i < cut_bc:
            fs.tier = "B"
        else:
            fs.tier = "C"

    return scores

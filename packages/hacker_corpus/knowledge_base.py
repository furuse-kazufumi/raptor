"""
KnowledgeBase — tag-based corpus hint retrieval for SourceHunt.

Priority:
  1. .claude/skills/corpus/hacker_corpus/ skill hierarchy (corpus2skill output)
  2. D:/docs/hacker_corpus/ raw files (fetched by hacker_corpus sources)
  3. None (no corpus available → empty hints)

This module is intentionally import-safe: callers must catch all exceptions.
"""

from __future__ import annotations

import os
import functools
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Tag → keyword mappings
# ---------------------------------------------------------------------------

TAG_KEYWORDS: dict[str, list[str]] = {
    "memory_unsafe": [
        "buffer overflow", "use-after-free", "heap", "double-free",
        "memory corruption", "stack overflow", "integer overflow",
        "off-by-one", "memcpy", "strcpy",
    ],
    "crypto": [
        "cryptograph", "timing attack", "nonce", "side channel",
        "weak cipher", "padding oracle", "key management", "AES", "RSA",
    ],
    "auth_boundary": [
        "authentication", "authorization", "privilege escalation",
        "access control", "bypass", "TOCTOU", "race condition",
    ],
    "parser": [
        "format string", "injection", "off-by-one", "deserialization",
        "truncation", "integer overflow", "parser",
    ],
    "syscall_entry": [
        "kernel", "syscall", "ioctl", "privilege escalation",
        "LPE", "kernel exploit", "copy_from_user",
    ],
    "fuzzable": [
        "fuzzing", "input validation", "boundary", "sanitization",
    ],
    "web": [
        "XSS", "SQL injection", "SSRF", "CSRF", "path traversal", "injection",
    ],
}

# Map corpus source directory names to the tags they are most useful for
_CORPUS_DIR_TAG_AFFINITY: dict[str, list[str]] = {
    "phrack":                  ["memory_unsafe", "syscall_entry", "parser", "crypto"],
    "ghsa":                    ["auth_boundary", "web", "crypto", "parser"],
    "capec":                   ["auth_boundary", "web", "parser", "memory_unsafe"],
    "d3fend":                  ["auth_boundary", "crypto"],
    "oss_security":            ["memory_unsafe", "syscall_entry", "crypto", "auth_boundary"],
    "project_zero":            ["memory_unsafe", "syscall_entry", "auth_boundary", "parser"],
    "book_of_secret_knowledge": ["auth_boundary", "web", "fuzzable", "parser", "crypto",
                                 "memory_unsafe", "syscall_entry"],
    # PayloadsAllTheThings: attack payload collection (65 categories, web-focused)
    "payloads_all_the_things": ["web", "parser", "auth_boundary", "fuzzable",
                                "crypto", "memory_unsafe"],
    # Awesome-LLM: curated LLM papers, models, tools, frameworks
    # Useful for RAD AI/LLM research context and llive/llmesh background knowledge
    "awesome_llm":             ["fuzzable"],  # minimal overlap with security tags;
                                              # primary use is RAD LLM/AI research context
}


# ---------------------------------------------------------------------------
# KnowledgeBase
# ---------------------------------------------------------------------------

class KnowledgeBase:
    """Tag-based corpus hint retrieval.

    Tries to load hints from (in priority order):
      1. A corpus2skill skill directory (SKILL.md hierarchy)
      2. Raw corpus files (plain text / JSON files per source)
    """

    def __init__(
        self,
        skill_dir: Optional[Path] = None,
        corpus_dir: Optional[Path] = None,
    ) -> None:
        self._skill_dir: Optional[Path] = skill_dir if (skill_dir and skill_dir.exists()) else None
        self._corpus_dir: Optional[Path] = corpus_dir if (corpus_dir and corpus_dir.exists()) else None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def auto_discover(cls) -> "Optional[KnowledgeBase]":
        """Auto-detect skill directory and corpus directory from environment.

        Returns None when neither source is available.
        """
        raptor_dir = os.environ.get("RAPTOR_DIR")

        skill_dir: Optional[Path] = None
        if raptor_dir:
            candidate = Path(raptor_dir) / ".claude" / "skills" / "corpus" / "hacker_corpus"
            if candidate.exists():
                skill_dir = candidate

        corpus_dir_override = os.environ.get("RAPTOR_CORPUS_DIR")
        if corpus_dir_override:
            corpus_dir = Path(corpus_dir_override)
        else:
            corpus_dir = Path("D:/docs/hacker_corpus")

        corpus_dir_resolved: Optional[Path] = corpus_dir if corpus_dir.exists() else None

        if skill_dir is None and corpus_dir_resolved is None:
            return None

        return cls(skill_dir=skill_dir, corpus_dir=corpus_dir_resolved)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_hints(self, tags, max_chars: int = 2000) -> str:
        """Return corpus knowledge relevant to the given tags.

        Args:
            tags: frozenset, set, list, or tuple of tag strings.
            max_chars: Maximum length of returned string.

        Returns:
            A string with relevant excerpts, or "" if nothing found.
        """
        if not isinstance(tags, frozenset):
            tags = frozenset(tags)
        return self._get_hints_cached(tags, max_chars)

    # Accepts a regular set for convenience — convert and delegate to cached method
    def get_hints_for_set(self, tags: set[str], max_chars: int = 2000) -> str:
        """Convenience wrapper accepting a mutable set."""
        return self.get_hints(frozenset(tags), max_chars)

    # ------------------------------------------------------------------
    # Internal (cached)
    # ------------------------------------------------------------------

    @functools.lru_cache(maxsize=128)
    def _get_hints_cached(self, tags: frozenset[str], max_chars: int) -> str:
        keywords = self._expand_keywords(tags)
        if not keywords:
            return ""

        # Priority 1: skill directory
        if self._skill_dir is not None:
            result = self._hints_from_skill_dir(keywords, max_chars)
            if result:
                return result

        # Priority 2: raw corpus files
        if self._corpus_dir is not None:
            result = self._hints_from_corpus_dir(tags, keywords, max_chars)
            if result:
                return result

        return ""

    # ------------------------------------------------------------------
    # Keyword expansion
    # ------------------------------------------------------------------

    @staticmethod
    def _expand_keywords(tags: frozenset[str]) -> list[str]:
        seen: set[str] = set()
        keywords: list[str] = []
        for tag in tags:
            for kw in TAG_KEYWORDS.get(tag, []):
                kw_lower = kw.lower()
                if kw_lower not in seen:
                    seen.add(kw_lower)
                    keywords.append(kw)
        return keywords

    # ------------------------------------------------------------------
    # Source: skill directory (corpus2skill SKILL.md)
    # ------------------------------------------------------------------

    def _hints_from_skill_dir(self, keywords: list[str], max_chars: int) -> str:
        # Each cluster subdirectory has a SKILL.md with rich Key Knowledge text.
        # Scan all top-level cluster dirs and collect matching sections.
        cluster_dirs = sorted(
            d for d in self._skill_dir.iterdir() if d.is_dir()
        )

        collected: list[str] = []
        budget = max_chars
        for cluster_dir in cluster_dirs:
            if budget <= 0:
                break
            skill_md = cluster_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            try:
                text = skill_md.read_text(encoding="utf-8")
            except OSError:
                continue
            excerpt = self._extract_matching_sections(text, keywords, min(600, budget))
            if excerpt:
                collected.append(f"[{cluster_dir.name}]\n{excerpt}")
                budget -= len(collected[-1])

        return "\n\n".join(collected)[:max_chars]

    @staticmethod
    def _extract_matching_sections(text: str, keywords: list[str], max_chars: int) -> str:
        """Extract sections from markdown text that contain any keyword."""
        kw_lower = [k.lower() for k in keywords]
        sections: list[str] = []
        current: list[str] = []
        current_matches = False

        for line in text.splitlines(keepends=True):
            if line.startswith("#"):
                # Flush previous section if it matched
                if current_matches and current:
                    sections.append("".join(current))
                current = [line]
                current_matches = any(k in line.lower() for k in kw_lower)
            else:
                current.append(line)
                if not current_matches:
                    if any(k in line.lower() for k in kw_lower):
                        current_matches = True

        # Flush last section
        if current_matches and current:
            sections.append("".join(current))

        combined = "\n".join(sections)
        return combined[:max_chars] if combined else ""

    # ------------------------------------------------------------------
    # Source: raw corpus files
    # ------------------------------------------------------------------

    def _hints_from_corpus_dir(
        self,
        tags: frozenset[str],
        keywords: list[str],
        max_chars: int,
    ) -> str:
        """Sample raw corpus files matching the given tags and keywords."""
        if self._corpus_dir is None:
            return ""

        # Determine which source subdirectories are relevant to our tags
        relevant_dirs: list[Path] = []
        for source_name, source_tags in _CORPUS_DIR_TAG_AFFINITY.items():
            if any(t in tags for t in source_tags):
                candidate = self._corpus_dir / source_name
                if candidate.exists() and candidate.is_dir():
                    relevant_dirs.append(candidate)

        if not relevant_dirs:
            # Fall back: search all subdirectories
            relevant_dirs = [
                d for d in self._corpus_dir.iterdir()
                if d.is_dir()
            ]

        kw_lower = [k.lower() for k in keywords]
        collected: list[str] = []
        budget = max_chars

        for src_dir in relevant_dirs:
            if budget <= 0:
                break
            excerpt = self._sample_dir(src_dir, kw_lower, budget)
            if excerpt:
                collected.append(excerpt)
                budget -= len(excerpt)

        return "\n\n".join(collected)[:max_chars]

    @staticmethod
    def _sample_dir(directory: Path, kw_lower: list[str], budget: int) -> str:
        """Read up to a few files from a directory, returning keyword-matching snippets."""
        # Prefer .txt and .md files; fall back to .json
        files: list[Path] = []
        for ext in ("*.txt", "*.md", "*.json"):
            files.extend(directory.glob(ext))
            if len(files) >= 10:
                break

        # Sort by modification time (newest first — most recent research)
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        snippets: list[str] = []
        chars_used = 0
        for fpath in files[:5]:  # sample at most 5 files per source
            if chars_used >= budget:
                break
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            snippet = _extract_snippet(text, kw_lower, max_chars=min(400, budget - chars_used))
            if snippet:
                label = f"[{fpath.parent.name}/{fpath.name}]"
                entry = f"{label}\n{snippet}"
                snippets.append(entry)
                chars_used += len(entry)

        return "\n".join(snippets)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _extract_snippet(text: str, kw_lower: list[str], max_chars: int = 400) -> str:
    """Return a snippet of text around the first keyword match."""
    text_lower = text.lower()
    best_pos = -1
    for kw in kw_lower:
        pos = text_lower.find(kw)
        if pos != -1:
            if best_pos == -1 or pos < best_pos:
                best_pos = pos

    if best_pos == -1:
        return ""

    # Return a window around the match
    start = max(0, best_pos - 100)
    end = min(len(text), best_pos + max_chars)
    return text[start:end].strip()

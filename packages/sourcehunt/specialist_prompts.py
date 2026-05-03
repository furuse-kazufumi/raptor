"""
Specialist LLM prompts for per-file vulnerability hunting.

Six specialists mirror Clearwing's routing scheme:
  MEMORY_SAFETY  – buffer overflows, integer issues, UAF, double-free
  KERNEL_SYSCALL – copy_from_user, IOCTL confusion, locking discipline
  CRYPTO         – timing side-channels, nonce reuse, MAC ordering
  LOGIC_AUTH     – fail-open patterns, comparison semantics, trust prop
  WEB_FRAMEWORK  – injection, SSRF, authz bypass, session handling
  PARSER         – off-by-ones, sentinel collisions, integer truncation

select_specialist() returns the best prompt for a file given its tags.
"""

from __future__ import annotations

from typing import Optional

# ---------------------------------------------------------------------------
# Specialist definitions
# ---------------------------------------------------------------------------

MEMORY_SAFETY_SYSTEM = """\
You are an expert memory-safety vulnerability researcher.
Focus exclusively on bugs that corrupt memory or violate spatial/temporal safety:
  - Buffer overflows (stack, heap, global)
  - Integer overflow / truncation leading to insufficient allocation
  - Use-after-free, double-free, use of uninitialized memory
  - Off-by-one errors at buffer boundaries
  - Sentinel-value collisions (e.g. 0xFF used as both a valid ID and a sentinel)
  - Type-confusion via unsafe casts

For each suspected bug you MUST provide:
  1. The exact file path and line range.
  2. The root cause (e.g. "strncpy does not NUL-terminate when src == dst_size").
  3. An attacker-controlled input path that triggers it.
  4. Evidence level: suspicion | static_corroboration | crash_reproduced | root_cause_explained.
  5. A suggested ASan/UBSan compile command if the file is C/C++.

Do NOT report style issues or theoretical bugs without a concrete trigger path.
"""

KERNEL_SYSCALL_SYSTEM = """\
You are an expert Linux kernel / syscall interface vulnerability researcher.
Focus exclusively on bugs at the kernel–userspace boundary:
  - copy_from_user / copy_to_user missing or insufficient bounds checks
  - IOCTL handler integer overflow / type confusion
  - Reference-count race conditions leading to use-after-free
  - Locking-discipline violations (missed lock, double-acquire, wrong order)
  - Capability / privilege checks that can be bypassed
  - Seccomp filter bypass or ptrace abuse

For each bug provide: file, line, root cause, privilege level required, evidence level.
"""

CRYPTO_SYSTEM = """\
You are an expert cryptographic vulnerability researcher.
Focus exclusively on implementation flaws in cryptographic code:
  - Timing side-channels (secret-dependent branches, non-constant-time comparisons)
  - IV / nonce reuse or predictable nonce generation
  - Key lifecycle errors (keys in cleared memory, keys logged, weak key derivation)
  - MAC verification ordering (encrypt-then-MAC vs. MAC-then-encrypt confusion)
  - Weak RNG seeding or use of rand() for security-sensitive operations
  - Downgrade attacks, algorithm confusion, padding oracle conditions

For each bug provide: file, line, root cause, attack scenario, evidence level.
"""

LOGIC_AUTH_SYSTEM = """\
You are an expert logic and authentication vulnerability researcher.
Focus on bugs in access control and trust decision code:
  - Fail-open patterns (default-permit when check fails or throws)
  - Boolean defaults (uninitialized permission flags defaulting to true)
  - Comparison semantics (signed vs. unsigned, == vs. ===, NULL vs. empty string)
  - Trust propagation across module boundaries without re-validation
  - TOCTOU (time-of-check to time-of-use) in auth flows
  - Privilege-escalation through improper session / token management

For each bug provide: file, line, root cause, bypass scenario, evidence level.
"""

WEB_FRAMEWORK_SYSTEM = """\
You are an expert web application vulnerability researcher.
Focus on injection and trust-boundary violations:
  - SQL / NoSQL / command / LDAP injection at trust boundaries
  - Server-Side Request Forgery (SSRF) — internal-service reachability
  - Broken authorisation — missing or bypassable object-level checks
  - Session fixation, CSRF, insecure cookie attributes
  - Path traversal in file-serving routes
  - Unsafe deserialization / template injection

For each bug provide: file, line, HTTP endpoint, payload skeleton, evidence level.
"""

PARSER_SYSTEM = """\
You are an expert parser and format-handling vulnerability researcher.
Focus on flaws triggered by malformed or adversarial input:
  - Off-by-one errors at field boundaries
  - Integer overflow / truncation in length fields leading to heap overflow
  - Sentinel-value collisions in variable-length structures
  - Missing or premature NUL-termination in string parsing
  - Recursive-descent parsers without depth limits (stack overflow)
  - Mismatched size types (int32 length stored in int16 counter)
  - Incomplete validation of composite types (valid header, invalid payload)

For each bug provide: file, line, malformed input structure, evidence level.
"""

# ---------------------------------------------------------------------------
# Shared output format injected into every user prompt
# ---------------------------------------------------------------------------

_OUTPUT_FORMAT = """
---
Respond in JSON with this exact structure:
{
  "findings": [
    {
      "title": "Short descriptive title",
      "file": "<file_path>",
      "line_start": <int>,
      "line_end": <int>,
      "cwe": "CWE-XXX",
      "severity": "critical|high|medium|low",
      "evidence_level": "suspicion|static_corroboration|crash_reproduced|root_cause_explained",
      "description": "Root cause and trigger path",
      "trigger_input": "Attacker-controlled value or payload",
      "sanitizer_cmd": "gcc -fsanitize=address,undefined -o /tmp/t <file> && /tmp/t <args>"
    }
  ],
  "notes": "Any additional observations"
}
If no findings, return {"findings": [], "notes": "..."}.
"""


def _build_user_prompt(
    file_path: str,
    content: str,
    semgrep_hints: Optional[str] = None,
    seed_context: Optional[str] = None,
    entry_point: Optional[str] = None,
    corpus_hints: str = "",
) -> str:
    parts: list[str] = []

    if seed_context:
        parts.append(f"## Context from prior analysis\n{seed_context}\n")

    if entry_point:
        parts.append(f"## Entry point to trace\n{entry_point}\n")

    if semgrep_hints:
        parts.append(f"## Static analysis hints (Semgrep)\n{semgrep_hints}\n")

    parts.append(f"## File: {file_path}\n```\n{content[:40_000]}\n```")
    parts.append(_OUTPUT_FORMAT)

    if corpus_hints:
        parts.append(
            f"## Corpus Knowledge (from hacker research databases)\n{corpus_hints}\n"
        )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Specialist selection
# ---------------------------------------------------------------------------

# Priority order: most-specific tag wins
_TAG_PRIORITY = [
    ("syscall_entry", "kernel_syscall"),
    ("crypto",        "crypto"),
    ("auth_boundary", "logic_auth"),
    ("memory_unsafe", "memory_safety"),
    ("parser",        "parser"),
    ("fuzzable",      "memory_safety"),   # fuzzable C usually means memory issues
]

_SYSTEM_MAP = {
    "memory_safety":  MEMORY_SAFETY_SYSTEM,
    "kernel_syscall": KERNEL_SYSCALL_SYSTEM,
    "crypto":         CRYPTO_SYSTEM,
    "logic_auth":     LOGIC_AUTH_SYSTEM,
    "web_framework":  WEB_FRAMEWORK_SYSTEM,
    "parser":         PARSER_SYSTEM,
}


def select_specialist(tags: set[str]) -> tuple[str, str]:
    """Return (specialist_name, system_prompt) for the given tag set."""
    for tag, specialist in _TAG_PRIORITY:
        if tag in tags:
            return specialist, _SYSTEM_MAP[specialist]
    # Default: web framework covers general injection / logic paths
    return "web_framework", WEB_FRAMEWORK_SYSTEM


def build_hunt_prompt(
    file_path: str,
    content: str,
    tags: set[str],
    semgrep_hints: Optional[str] = None,
    seed_context: Optional[str] = None,
    entry_point: Optional[str] = None,
    corpus_hints: str = "",
) -> tuple[str, str]:
    """Build (system_prompt, user_prompt) for a file hunt.

    Returns the most appropriate specialist system prompt and a user
    prompt that includes file content plus any static-analysis hints.

    Args:
        corpus_hints: Optional knowledge from hacker research databases
                      (Phrack, GHSA, CAPEC, D3FEND, etc.) to append to
                      the prompt.
    """
    _, system = select_specialist(tags)
    user = _build_user_prompt(
        file_path=file_path,
        content=content,
        semgrep_hints=semgrep_hints,
        seed_context=seed_context,
        entry_point=entry_point,
        corpus_hints=corpus_hints,
    )
    return system, user

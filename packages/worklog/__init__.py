"""raptor work-graph orchestration package.

A durable work-graph (SQLite/WAL) that lets 3+ heterogeneous models/NNs
(Claude / Codex / local Ollama / Copilot) grind endlessly on a shared body of
work. The graph is the system-of-record; sessions are disposable, crash-only
workers that lease a node, do bounded work, journal the result, and die.
"Endless" is a property of the graph + an external driver — never of any one
session (Claude cannot self-restart; the driver owns restart authority and
halts at the auth gate).

See docs/superpowers/specs/2026-07-29-graph-orchestration-design.md.
"""

from __future__ import annotations

__all__ = [
    "compact",
    "corpus",
    "driver",
    "routing",
    "seed",
    "store",
    "validate",
    "workers",
]

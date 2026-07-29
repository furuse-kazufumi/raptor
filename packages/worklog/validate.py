"""Fail-closed invariants for the work-graph.

Per raptor MCP rules: validation failures are rejected, not passed through.
All enums are closed and snake_case (raptor OUTPUT STYLE — no ALL_CAPS, no
red/green semantics). Cycle detection guards the scheduler's DAG so a bad
dependency edge (possibly proposed by a heterogeneous model) can never deadlock
the loop forever.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

# ── Closed vocabularies ────────────────────────────────────────────────
STATUS = frozenset({"pending", "ready", "leased", "blocked", "done", "failed"})

# Terminal states never transition further.
TERMINAL = frozenset({"done", "failed"})

EVENT_KINDS = frozenset(
    {
        "created",
        "ready",
        "leased",
        "lease_expired",
        "done",
        "failed",
        "verified",
        "blocked",
        "escalated",
        "unblocked",
    }
)

# Capability tags a task may carry; workers advertise which they satisfy.
CAPABILITIES = frozenset(
    {
        "scan",       # deterministic tool (Semgrep/OSV), no LLM
        "triage",     # classify / dedup / tag — cheap local
        "summarize",  # extract / condense — local
        "codegen",    # patch / code draft
        "reason",     # deep reasoning / planning — Claude tier
        "review",     # verify (must be a different provider than author)
        "web",        # broad web research
    }
)

CONSTRAINTS = frozenset(
    {
        "no-push",
        "read-only",
        "needs-human-judgment",
        "on-prem-only",
    }
)


class InvariantError(ValueError):
    """A fail-closed invariant was violated."""


# ── Provider / locality ────────────────────────────────────────────────
def is_local_model(model: str | None) -> bool:
    """True iff the model runs on-box (no data egress). Only Ollama is local."""
    if not model:
        return False
    return model.lower().startswith("ollama")


def provider_of(model: str | None) -> str:
    """Coarse provider family for the different-provider verification gate.

    'ollama:qwen2.5:14b' -> 'ollama'; 'claude' -> 'claude'; 'codex' -> 'codex'.
    """
    if not model:
        return ""
    return model.split(":", 1)[0].strip().lower()


# ── Enum guards ────────────────────────────────────────────────────────
def check_status(status: str) -> str:
    if status not in STATUS:
        raise InvariantError(f"invalid status: {status!r} (allowed: {sorted(STATUS)})")
    return status


def check_event_kind(kind: str) -> str:
    if kind not in EVENT_KINDS:
        raise InvariantError(f"invalid event kind: {kind!r}")
    return kind


def check_capabilities(caps: Iterable[str]) -> list[str]:
    out = []
    for c in caps:
        if c not in CAPABILITIES:
            raise InvariantError(f"invalid capability tag: {c!r} (allowed: {sorted(CAPABILITIES)})")
        out.append(c)
    return out


# ── Cycle detection ────────────────────────────────────────────────────
def has_cycle(deps: Mapping[str, Sequence[str]]) -> bool:
    """True iff the depends_on graph contains a cycle.

    `deps` maps task_id -> list of task_ids it depends on. Edges to unknown
    nodes are ignored (a task may depend on an id not yet materialized).
    Iterative DFS with a 3-color marking to stay safe on deep graphs.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in deps}

    for root in deps:
        if color[root] != WHITE:
            continue
        # stack holds (node, iterator_started) — emulate recursion
        stack: list[str] = [root]
        it_stack: list[list[str]] = [list(deps.get(root, ()))]
        color[root] = GRAY
        while stack:
            node = stack[-1]
            successors = it_stack[-1]
            if successors:
                nxt = successors.pop()
                if nxt not in color:  # unknown target node — treat as leaf
                    continue
                if color[nxt] == GRAY:
                    return True
                if color[nxt] == WHITE:
                    color[nxt] = GRAY
                    stack.append(nxt)
                    it_stack.append(list(deps.get(nxt, ())))
            else:
                color[node] = BLACK
                stack.pop()
                it_stack.pop()
    return False


def would_create_cycle(
    deps: Mapping[str, Sequence[str]], new_from: str, new_to: str
) -> bool:
    """True iff adding edge new_from -> new_to (new_from depends_on new_to)
    would create a cycle in the existing deps graph."""
    if new_from == new_to:
        return True
    merged: dict[str, list[str]] = {k: list(v) for k, v in deps.items()}
    merged.setdefault(new_from, [])
    if new_to not in merged[new_from]:
        merged[new_from].append(new_to)
    merged.setdefault(new_to, merged.get(new_to, []))
    return has_cycle(merged)


def topological_order(deps: Mapping[str, Sequence[str]]) -> list[str]:
    """Kahn's algorithm. Returns nodes in dependency order (a task appears
    after all tasks it depends on). Raises InvariantError on a cycle."""
    # Build in-degree over known nodes only.
    nodes = set(deps)
    for targets in deps.values():
        nodes.update(t for t in targets)
    indeg: dict[str, int] = {n: 0 for n in nodes}
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for src, targets in deps.items():
        for tgt in targets:
            if tgt in nodes:
                # edge tgt -> src (tgt must come before src)
                adj[tgt].append(src)
                indeg[src] += 1
    queue = sorted(n for n in nodes if indeg[n] == 0)
    order: list[str] = []
    while queue:
        n = queue.pop(0)
        order.append(n)
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                # keep deterministic order
                queue.append(m)
                queue.sort()
    if len(order) != len(nodes):
        raise InvariantError("dependency graph has a cycle; no topological order")
    return order

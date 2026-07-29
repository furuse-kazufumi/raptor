"""Seed the work-graph from claude-projects.json.

Migrates the existing project graph into `task` nodes (idempotently), so the
work-graph starts populated with real work rather than a toy. Each project's
`next_plan` becomes a task `spec`; `_priority` order becomes `priority`;
`plan_ref` is carried as a reference in the spec. These seeded tasks carry the
`reason` capability and are therefore honestly routed to the human-gated Claude
tier (spec §2.3–2.4) — the "don't consume the session" win comes from *cheap*
tasks (triage/summarize), which a planning session adds separately.

`claude-projects.json` is read as UTF-8 explicitly (Windows PowerShell / default
ANSI would mojibake the Japanese and break JSON parsing).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .store import WorkGraph


def _load_projects(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _priority_ranks(meta: dict[str, Any], project_keys: list[str]) -> dict[str, int]:
    """Derive 1..N priority from the `_priority` order string, else stable order."""
    prio_str = str(meta.get("_priority", "")).lower()

    def first_index(key: str) -> int:
        name = str(meta.get(key, {}).get("name", "")).lower()
        idxs = [prio_str.find(x) for x in (key.lower(), name) if x]
        idxs = [i for i in idxs if i >= 0]
        return min(idxs) if idxs else 10**9

    ordered = sorted(project_keys, key=lambda k: (first_index(k), k))
    return {k: i + 1 for i, k in enumerate(ordered)}


def project_keys(meta: dict[str, Any]) -> list[str]:
    """Real project keys (skip the _-prefixed metadata comment keys)."""
    return [
        k
        for k, v in meta.items()
        if not k.startswith("_") and isinstance(v, dict) and v.get("next_plan")
    ]


def seed_from_projects(wg: WorkGraph, projects_json: str | Path) -> list[str]:
    """Idempotently create one `reason`-tier task per project. Returns task ids."""
    path = Path(projects_json)
    meta = _load_projects(path)
    keys = project_keys(meta)
    ranks = _priority_ranks(meta, keys)

    created: list[str] = []
    for key in keys:
        p = meta[key]
        name = p.get("name", key)
        next_plan = str(p.get("next_plan", "")).strip()
        plan_ref = str(p.get("plan_ref", "")).strip()
        if not next_plan:
            continue
        spec = next_plan
        if plan_ref:
            spec += f"\n\n---\n(plan_ref: {plan_ref} — 詳細/戦略の正本はここ)"
        tid = wg.add_task(
            task_id=f"seed-{key}",
            project=key,
            title=f"{name}: next_plan",
            spec=spec,
            priority=ranks.get(key, 5),
            capability=["reason"],
            on_prem_only=False,
            constraints=["no-push", "needs-human-judgment"],
        )
        created.append(tid)
    return created

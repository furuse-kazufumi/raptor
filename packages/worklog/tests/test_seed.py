"""Seeding from a claude-projects.json-shaped file."""

import json

from packages.worklog import seed as seed_mod
from packages.worklog.store import WorkGraph


def _write_projects(tmp_path):
    meta = {
        "_schema": "comment key, ignored",
        "_priority": "priority (fixed): Alpha > Beta > Gamma > その他",
        "alpha": {"name": "Alpha", "next_plan": "do alpha work", "plan_ref": "memory:a"},
        "beta": {"name": "Beta", "next_plan": "do beta work"},
        "gamma": {"name": "Gamma", "next_plan": "do gamma work"},
        "empty": {"name": "Empty (no plan)"},  # skipped: no next_plan
    }
    p = tmp_path / "claude-projects.json"
    p.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return p


def test_seed_creates_tasks_with_priority_order(tmp_path):
    projects = _write_projects(tmp_path)
    wg = WorkGraph(tmp_path / "wg.db")
    try:
        ids = seed_mod.seed_from_projects(wg, projects)
        assert set(ids) == {"seed-alpha", "seed-beta", "seed-gamma"}
        assert wg.get("seed-alpha")["priority"] == 1
        assert wg.get("seed-beta")["priority"] == 2
        assert wg.get("seed-gamma")["priority"] == 3
        # empty project skipped
        assert wg.get("seed-empty") is None
        # reason-tier, human-gated constraints
        t = wg.get("seed-alpha")
        assert t["capability"] == ["reason"]
        assert "needs-human-judgment" in t["constraints"]
        assert "memory:a" in t["spec"]
    finally:
        wg.close()


def test_seed_is_idempotent(tmp_path):
    projects = _write_projects(tmp_path)
    wg = WorkGraph(tmp_path / "wg.db")
    try:
        seed_mod.seed_from_projects(wg, projects)
        seed_mod.seed_from_projects(wg, projects)
        assert len(wg.all_tasks()) == 3  # no duplicates on re-seed
    finally:
        wg.close()

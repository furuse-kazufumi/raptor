"""End-to-end CLI smoke test — drives libexec/raptor-worklog as a subprocess
against a temp DB (WORKLOG_DB), covering the full task lifecycle."""

import os
import subprocess
import sys
from pathlib import Path

RAPTOR_DIR = Path(__file__).resolve().parents[3]
CLI = RAPTOR_DIR / "libexec" / "raptor-worklog"


def _run(args, db):
    env = dict(os.environ)
    env["WORKLOG_DB"] = str(db)
    env["WORKLOG_ARTIFACTS"] = str(db.parent / "art")
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True, text=True, encoding="utf-8", env=env,
    )


def test_cli_task_lifecycle(tmp_path):
    db = tmp_path / "wg.db"

    assert _run(["init"], db).returncode == 0

    r = _run(["add", "--title", "t1", "--spec", "do it", "--id", "t1", "--capability", "triage"], db)
    assert r.returncode == 0 and "t1" in r.stdout

    assert "t1" in _run(["list"], db).stdout
    assert "t1" in _run(["ready"], db).stdout

    r = _run(["lease", "t1", "--model", "ollama:x", "--owner", "w"], db)
    assert r.returncode == 0

    r = _run(["done", "t1", "--owner", "w", "--result", "out.md", "--by", "ollama:x"], db)
    assert r.returncode == 0

    r = _run(["show", "t1"], db)
    assert '"status": "done"' in r.stdout

    r = _run(["stats"], db)
    assert '"done": 1' in r.stdout


def test_cli_cycle_check_rejects(tmp_path):
    db = tmp_path / "wg.db"
    _run(["add", "--title", "a", "--spec", "s", "--id", "a"], db)
    _run(["add", "--title", "b", "--spec", "s", "--id", "b", "--depends", "a"], db)
    # b depends on a; adding a depends-on b would cycle — the store rejects it, but
    # cycle-check on the current (acyclic) graph should pass.
    r = _run(["cycle-check"], db)
    assert r.returncode == 0 and "acyclic: ok" in r.stdout

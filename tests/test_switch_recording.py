# SPDX-License-Identifier: Apache-2.0
"""記録ギャップ修正 (2026-07-11) の回帰テスト.

検証:
  A. 共有 resolver _raptor_active.resolve_active_project の優先順 (可変マーカー > env、非ccr=None)。
  B. libexec/raptor-switch の `.raptor-session.json` 書式 (ccr writeSessionConfig と同じ 7 キー)。

実行:
  py -3.11 tests/test_switch_recording.py
実マーカー (.raptor-session.json) には触れない (--config / tmp を使う)。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_RAPTOR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_RAPTOR / "libexec"))

import _raptor_active as A  # noqa: E402

_fails: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(f"  [{'ok' if cond else 'FAIL'}] {msg}")
    if not cond:
        _fails.append(msg)


def _write_marker(root: Path, project_path: Path | None) -> None:
    """<root>/.raptor-session.json を書く (resolver は parents[1] から辿る)。"""
    cfg = root / ".raptor-session.json"
    if project_path is None:
        cfg.unlink(missing_ok=True)
        return
    cfg.write_text(json.dumps({"projectName": project_path.name,
                               "projectPath": str(project_path)}), encoding="utf-8")


def test_resolver() -> None:
    print("A. resolve_active_project 優先順")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "libexec").mkdir()
        fake_script = str(root / "libexec" / "fake_hook")  # parents[1] == root
        proj_env = root / "proj_env"; proj_env.mkdir()
        proj_mark = root / "proj_marker"; proj_mark.mkdir()

        # A1: env 有 + マーカー別ディレクトリ → マーカー優先
        os.environ["RAPTOR_CALLER_DIR"] = str(proj_env)
        _write_marker(root, proj_mark)
        got = A.resolve_active_project(fake_script)
        check(got == proj_mark, f"marker が env より優先 (got={got})")

        # A2: env 有 + マーカー無し → env fallback
        _write_marker(root, None)
        got = A.resolve_active_project(fake_script)
        check(got == proj_env, f"マーカー欠落で env fallback (got={got})")

        # A3: env 有 + マーカーが非存在ディレクトリ → env fallback
        (root / ".raptor-session.json").write_text(
            json.dumps({"projectPath": str(root / "does_not_exist")}), encoding="utf-8")
        got = A.resolve_active_project(fake_script)
        check(got == proj_env, f"不正マーカーで env fallback (got={got})")

        # A4: env 無し → None (非 ccr は no-op)
        os.environ.pop("RAPTOR_CALLER_DIR", None)
        _write_marker(root, proj_mark)
        got = A.resolve_active_project(fake_script)
        check(got is None, f"env 無しは None=no-op (got={got})")


def test_raptor_switch() -> None:
    print("B. raptor-switch の書式 / fail-closed")
    switch = _RAPTOR / "libexec" / "raptor-switch"
    with tempfile.TemporaryDirectory() as td:
        projects = Path(td) / "projects"; projects.mkdir()
        (projects / "myproj").mkdir()
        cfg = Path(td) / "session.json"
        env = {**os.environ, "RAPTOR_PROJECTS_DIR": str(projects)}

        # B1: 有効な dirname → exit 0 + 7 キー書式
        r = subprocess.run(["py", "-3.11", str(switch), "myproj", "--config", str(cfg)],
                           capture_output=True, text=True, env=env)
        check(r.returncode == 0, f"有効 target で exit 0 (rc={r.returncode}, err={r.stderr.strip()[:120]})")
        if cfg.exists():
            data = json.loads(cfg.read_text(encoding="utf-8"))
            keys = {"projectName", "projectPath", "docsDir", "summaryFile",
                    "progressFile", "debugFile", "testFile"}
            check(set(data) == keys, f"7 キー完備 (got={sorted(data)})")
            check(data.get("projectName") == "myproj", f"projectName=myproj (got={data.get('projectName')})")
            check(Path(data.get("summaryFile", "")).name == "SESSION_SUMMARY.md",
                  "summaryFile が docs/SESSION_SUMMARY.md")
            check(Path(data.get("projectPath", "")).name == "myproj", "projectPath が対象ディレクトリ")
        else:
            check(False, "config が書かれた")

        # B2: 無効な target → 非0 + config 未変更 (fail-closed)
        cfg2 = Path(td) / "session2.json"
        r2 = subprocess.run(["py", "-3.11", str(switch), "no_such_proj", "--config", str(cfg2)],
                            capture_output=True, text=True, env=env)
        check(r2.returncode != 0, f"無効 target で 非0 (rc={r2.returncode})")
        check(not cfg2.exists(), "無効時は config を書かない (fail-closed)")


def main() -> int:
    test_resolver()
    test_raptor_switch()
    print()
    if _fails:
        print(f"FAILED: {len(_fails)} 件")
        for f in _fails:
            print(f"  - {f}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

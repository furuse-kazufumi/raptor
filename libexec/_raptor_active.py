# SPDX-License-Identifier: Apache-2.0
"""RAPTOR Stop hook が共有する「今アクティブなプロジェクト」リゾルバ.

背景 (2026-07-11): セッション中に別プロジェクトへ切り替えると、Stop hook
(raptor-auto-summary / raptor-next-session-update) が起動時プロジェクト固定の
環境変数 RAPTOR_CALLER_DIR しか見ず、切り替え先の継続記録が残らなかった。

解決: 「今アクティブなプロジェクト」を単一の**可変マーカー** `.raptor-session.json`
(projectPath) から解決する。このファイルは ccr ランチャーが起動時に書き、`/switch`
(libexec/raptor-switch) がセッション中に更新する。RAPTOR_CALLER_DIR は不変 (env は
プロセス寿命で固定) なので後方互換の fallback として残す。

優先順:
  1. `.raptor-session.json` の projectPath ── 可変 (起動時ランチャー / セッション中 /switch)
  2. RAPTOR_CALLER_DIR (env)               ── 起動時固定
起動直後はマーカー == env なので **挙動不変**。/switch 後のみマーカーが先行し記録が追従する。
非 ccr (env 未設定) は None を返し、従来どおり no-op (stale マーカーで誤ルーティングしない)。
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def raptor_dir(script_file: str) -> Path:
    """libexec/<script> から RAPTOR ルート (parents[1]) を自己解決 (RAPTOR_DIR 非依存)。"""
    return Path(script_file).resolve().parents[1]


def read_marker_project(script_file: str) -> Path | None:
    """`.raptor-session.json` の projectPath を Path で返す (欠落/不正/非ディレクトリは None)。"""
    marker = raptor_dir(script_file) / ".raptor-session.json"
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    raw = data.get("projectPath") if isinstance(data, dict) else None
    if not raw or not isinstance(raw, str):
        return None
    try:
        path = Path(raw)
    except (TypeError, ValueError):
        return None
    return path if path.is_dir() else None


def resolve_active_project(script_file: str) -> Path | None:
    """今アクティブなプロジェクトパスを解決する (優先: 可変マーカー > env)。

    ccr セッション (RAPTOR_CALLER_DIR 有) のみ動作。起動直後はマーカー==env で挙動不変、
    /switch 後はマーカーが先行して記録が追従する。非 ccr (env 無) は None (従来の no-op)。
    """
    env = os.environ.get("RAPTOR_CALLER_DIR")
    if not env:
        return None
    marker = read_marker_project(script_file)
    if marker is not None:
        return marker
    env_path = Path(env)
    return env_path if env_path.is_dir() else None

"""RAPTOR Telegram notification module.

Sends scan completion, high-risk findings, and pipeline events to Telegram.
Uses TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from environment.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional


def _bot_token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _chat_id() -> str:
    return os.environ.get("TELEGRAM_CHAT_ID", "8731660763")


def is_configured() -> bool:
    return bool(_bot_token())


def send(text: str, chat_id: Optional[str] = None) -> bool:
    """Send a Telegram message. Returns True on success."""
    token = _bot_token()
    if not token:
        return False
    cid = chat_id or _chat_id()
    try:
        result = subprocess.run(
            ["curl", "-s", "-X", "POST",
             f"https://api.telegram.org/bot{token}/sendMessage",
             "-d", f"chat_id={cid}",
             "--data-urlencode", f"text={text}"],
            capture_output=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def notify_scan_complete(command: str, target: str, out_dir: str,
                         findings: int = 0, elapsed: float = 0.0) -> None:
    """Notify on scan/analysis completion."""
    if not is_configured():
        return
    emoji = "⚠️" if findings > 0 else "✓"
    msg = (
        f"{emoji} RAPTOR {command} 完了\n"
        f"対象: {Path(target).name}\n"
        f"発見: {findings} 件\n"
        f"時間: {elapsed:.0f}s\n"
        f"出力: {out_dir}"
    )
    send(msg)


def notify_high_risk(command: str, target: str, finding_title: str,
                     severity: str, out_dir: str) -> None:
    """Notify on high/critical severity finding."""
    if not is_configured():
        return
    msg = (
        f"🚨 高リスク発見 [{severity}]\n"
        f"コマンド: {command}\n"
        f"対象: {Path(target).name}\n"
        f"発見: {finding_title}\n"
        f"出力: {out_dir}"
    )
    send(msg)


def notify_pipeline_event(event: str, detail: str = "") -> None:
    """Notify on general pipeline events (start, error, etc.)."""
    if not is_configured():
        return
    msg = f"RAPTOR [{event}]\n{detail}" if detail else f"RAPTOR [{event}]"
    send(msg)

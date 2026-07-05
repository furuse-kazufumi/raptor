#!/usr/bin/env python3
"""fable-parity always-on gate (UserPromptSubmit hook).

Purpose
-------
Make the fable-parity orchestration gate *evaluated on every substantive turn*
when running on a weaker-per-pass model (Opus / local), WITHOUT paying overhead
on trivial turns. This is the honest reading of "常にオーケストラで動作する環境":
not "orchestrate everything unconditionally" (the skill's own parity-eval showed
a CEILING effect where that only adds cost), but "always CONSIDER the gate, and
route only tasks that actually clear it".

Contract (Claude Code UserPromptSubmit hook)
--------------------------------------------
- stdin: JSON with at least {"prompt": "<user text>", "hook_event_name": ...}.
- stdout: we emit a compact additionalContext reminder ONLY for substantive
  prompts. Trivial/lookup/slash-command turns emit nothing (zero token cost).
- exit 0 always (this hook never blocks a prompt).

Enablement
----------
Off by default so it is safe to ship globally (the user's global model is Fable,
which needs no scaffold). Turn it on for Opus/local sessions with:
    FABLE_PARITY_ALWAYS=1        (or =on / =true)
Optionally hard-disable regardless:
    FABLE_PARITY_ALWAYS=off
The ccr Opus fork can export this in .claude/raptor.env so every ccr session is
gated automatically.
"""
import json
import os
import re
import sys


def _enabled() -> bool:
    v = os.environ.get("FABLE_PARITY_ALWAYS", "").strip().lower()
    return v in ("1", "on", "true", "yes")


# --- trivial-prompt heuristics: if ANY match, we stay silent (no overhead) ----
_TRIVIAL_PATTERNS = [
    r"^\s*/",                       # slash command (/scan, /model, ...)
    r"^\s*!",                       # inline shell (! ...)
    r"^\s*(ls|cat|pwd|cd|head|tail|grep|find|rg|git status|git log)\b",
    r"^\s*(show|list|print|open|read|cat)\s+\S+$",
]
# Verbs/shape that signal a hard / high-stakes task worth gating.
_SUBSTANTIVE_HINTS = re.compile(
    r"(設計|方針|計画|検証|評価|分析|導出|証明|比較|移行|リファクタ|アーキ|"
    r"trade[- ]?off|矛盾|なぜ|理由|prove|derive|design|plan|migrat|architect|"
    r"root[- ]?cause|why|research|survey|prior[- ]?art|先行研究|調査|"
    r"exploit|脆弱性|vuln|threat|セキュリティ|review|監査|audit)",
    re.IGNORECASE,
)


def _is_trivial(prompt: str) -> bool:
    p = prompt.strip()
    if len(p) < 40:                       # short asks are almost always trivial
        return True
    for pat in _TRIVIAL_PATTERNS:
        if re.search(pat, p, re.IGNORECASE):
            return True
    return False


_REMINDER = (
    "[fable-parity gate] This turn looks substantive. Before answering, evaluate "
    "the 3-part gate (stakes AND single-pass-risk AND a verification asymmetry). "
    "If ALL hold, route to the matching fable-parity workflow "
    "(deep-reason / adversarial-verify / research(-verify) / plan(-critique|-verify)); "
    "requires /effort ultracode for the Workflow tool, else use the manual "
    "Agent-dispatch fallback. If ANY fails (trivial, pure knowledge gap, no "
    "check-cheaper-than-solve), answer directly — orchestration would only add "
    "cost. Do not claim 'Fable parity'; it is unmeasured."
)


def main() -> int:
    if not _enabled():
        return 0
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0  # fail-open: never block a prompt on a parse error
    prompt = str(data.get("prompt", "") or "")
    if not prompt or _is_trivial(prompt):
        return 0
    # Substantive by length; escalate the nudge if hard-task hints are present.
    context = _REMINDER
    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }
    try:
        sys.stdout.buffer.write((json.dumps(out) + "\n").encode("utf-8"))
    except Exception:
        sys.stdout.write(json.dumps(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

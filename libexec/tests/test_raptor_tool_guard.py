#!/usr/bin/env python3
"""raptor-tool-guard の検出ロジック検証。
実行: py -3.11 libexec/tests/test_raptor_tool_guard.py
(pytest 不要・stdlib のみ。拡張子なしの本体を importlib で読み込む。)
"""
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

GUARD = Path(__file__).resolve().parents[1] / "raptor-tool-guard"
_spec = importlib.util.spec_from_loader(
    "raptor_tool_guard", importlib.machinery.SourceFileLoader("raptor_tool_guard", str(GUARD))
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
evaluate = _mod.evaluate


def sev(findings):
    return {s for s, _ in findings}


def msgs(findings):
    return " || ".join(m for _, m in findings)


# (tool, command, expected_severity_or_None, substr_in_msg_or_None)
# expected: "block" = block 含む / "warn" = warn 含み block 無し / None = 検出ゼロ
CASES = [
    # ---- PowerShell BLOCK (そのシェルで確実に失敗) ----
    ("PowerShell", "head foo.txt", "block", "Get-Content"),
    ("PowerShell", "Get-Content x | tail -5", "block", "Tail"),
    ("PowerShell", "which python", "block", "Get-Command"),
    ("PowerShell", "touch newfile", "block", "New-Item"),
    ("PowerShell", "wc -l file", "block", "Measure-Object"),
    ("PowerShell", "rm -rf build", "block", "Recurse"),
    ("PowerShell", "mkdir -p a/b/c", "block", "Directory"),
    ("PowerShell", "ln -s a b", "block", "SymbolicLink"),
    ("PowerShell", "chmod 755 x", "block", "icacls"),
    ("PowerShell", "py script.py 2>/dev/null", "block", "$null"),
    ("PowerShell", "export FOO=bar", "block", "$env:"),
    ("PowerShell", "if [ -f x ]; then echo hi; fi", "block", "Test-Path"),
    ("PowerShell", "for f in *.txt; do echo $f; done", "block", "foreach"),
    ("PowerShell", "grep pattern file", "block", "Grep"),
    ("PowerShell", "sed s/a/b/ x", "block", "replace"),
    # ---- PowerShell WARN (動くが望ましくない) ----
    ("PowerShell", "cat config.json", "warn", "Read"),
    ("PowerShell", "Select-String -Pattern foo -Path *.py", "warn", "Grep"),
    ("PowerShell", "find . -name *.py", "warn", "Glob"),
    ("PowerShell", "python script.py", "warn", "py -3.11"),
    ("PowerShell", "Get-ChildItem -Recurse -Filter *.py", "warn", "Glob"),
    ("PowerShell", "git status", "warn", "rtk"),
    ("PowerShell", "FOO=bar py x.py", "warn", "インライン"),
    # ---- PowerShell ALLOW (検出ゼロ・FP 回避) ----
    ("PowerShell", "Get-ChildItem -Path . | Select-Object -First 5", None, None),
    ("PowerShell", 'Write-Output "tail -n 5 of the file"', None, None),  # tail はクォート内
    ("PowerShell", "rtk git status", None, None),  # rtk 前置済
    ("PowerShell", "py -3.11 -m pytest tests/", None, None),
    ("PowerShell", "$env:FOO='bar'", None, None),  # 正しい PS 代入
    ("PowerShell", '$path = "C:\\x"', None, None),  # 正しい PS 代入 (空白あり)
    ("PowerShell", "if ($x -eq 1) { Write-Output ok }", None, None),  # 正しい PS if
    # ---- Bash BLOCK (PowerShell/cmd 構文の混入) ----
    ("Bash", "Get-ChildItem -Recurse", "block", "cmdlet"),
    ("Bash", "Get-Content foo.txt", "block", "cmdlet"),
    ("Bash", "$env:PATH", "block", "PowerShell"),
    ("Bash", "$FOO = bar", "block", "代入"),
    ("Bash", "$x=5", "block", "代入"),
    # ---- Bash WARN ----
    ("Bash", "cat file.txt", "warn", "Read"),
    ("Bash", "grep -r foo .", "warn", "Grep"),
    ("Bash", "find . -name '*.py'", "warn", "Glob"),
    ("Bash", "python script.py", "warn", "py -3.11"),
    ("Bash", "cd /tmp && ls", "warn", "cd"),
    ("Bash", "git push --force origin main", "warn", "force"),
    ("Bash", "rm -rf /tmp/build", "warn", "不可逆"),
    ("Bash", "PYTHONUTF8=1 python x.py", "warn", "py -3.11"),
    # ---- Bash ALLOW (検出ゼロ・FP 回避) ----
    ("Bash", "py -3.11 -m pytest -q", None, None),
    ("Bash", 'echo "Get-Content is a cmdlet"', None, None),  # クォート内 cmdlet
    ("Bash", 'echo "use grep and find here"', None, None),  # クォート内
    ("Bash", "libexec/raptor-loop-queue peek", None, None),
    ("Bash", "rg 'pattern' src/", None, None),
    ("Bash", "ls -la", None, None),
    ("Bash", "[ $x = 1 ] && echo yes", None, None),  # bash テスト ($VAR= 誤検知回避)
    ("Bash", "PYTHONUTF8=1 py -3.11 x.py", None, None),  # env 前置 + py は OK
    # ---- 対象外ツールは常にゼロ ----
    ("Read", "head whatever", None, None),
    ("Bash", "", None, None),
]


def run():
    failures = []
    for tool, cmd, exp, substr in CASES:
        f = evaluate(tool, cmd)
        s = sev(f)
        ok = True
        detail = ""
        if exp is None:
            if f:
                ok = False
                detail = f"期待=検出ゼロ だが {s}: {msgs(f)}"
        elif exp == "block":
            if "block" not in s:
                ok = False
                detail = f"期待=block 含む だが {s or '検出ゼロ'}: {msgs(f)}"
        elif exp == "warn":
            if "warn" not in s or "block" in s:
                ok = False
                detail = f"期待=warn のみ だが {s or '検出ゼロ'}: {msgs(f)}"
        if ok and substr and substr not in msgs(f):
            ok = False
            detail = f"期待メッセージに `{substr}` 含む だが: {msgs(f)}"
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures.append((tool, cmd, detail))
        print(f"  [{status}] {tool:10} | {cmd[:48]:48} | {exp}")
    print()
    print(f"  {len(CASES) - len(failures)}/{len(CASES)} passed")
    if failures:
        print("\n  FAILURES:")
        for tool, cmd, detail in failures:
            print(f"   - {tool} `{cmd}`\n       {detail}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())

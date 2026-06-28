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
    ("PowerShell", "Get-Content config.yaml", "warn", "Read"),
    ("PowerShell", "python3 -m pytest -q", "warn", "py -3.11"),
    ("PowerShell", "FOO=bar py x.py", "warn", "インライン"),
    # ---- PowerShell ALLOW (検出ゼロ・FP 回避) ----
    ("PowerShell", "Get-ChildItem -Path . | Select-Object -First 5", None, None),
    ("PowerShell", 'Write-Output "tail -n 5 of the file"', None, None),  # tail はクォート内
    ("PowerShell", "rtk git status", None, None),  # rtk 前置済
    ("PowerShell", "py -3.11 -m pytest tests/", None, None),
    ("PowerShell", "$env:FOO='bar'", None, None),  # 正しい PS 代入
    ("PowerShell", '$path = "C:\\x"', None, None),  # 正しい PS 代入 (空白あり)
    ("PowerShell", "if ($x -eq 1) { Write-Output ok }", None, None),  # 正しい PS if
    ("PowerShell", "Get-Content log.txt | Select-Object -First 5", None, None),  # パイプ生成側→Read 警告抑制
    ("PowerShell", "foreach ($f in $files) { $f.Name }", None, None),  # PS foreach (bash for-in でない)
    ("PowerShell", "$count = 5; Write-Output $count", None, None),  # 正しい PS 代入
    ("PowerShell", "(mkdir -p build)", "block", "Directory"),  # subshell 括弧内の致命誤用 (FN 修正)
    # ---- Bash BLOCK (PowerShell/cmd 構文の混入) ----
    ("Bash", "Get-ChildItem -Recurse", "block", "cmdlet"),
    ("Bash", "Get-Content foo.txt", "block", "cmdlet"),
    ("Bash", "$env:PATH", "block", "PowerShell"),
    ("Bash", "$FOO = bar", "block", "代入"),
    ("Bash", "$x=5", "block", "代入"),
    ("Bash", "echo $env:USERPROFILE", "block", "PowerShell"),  # $env: idiom in bash
    ("Bash", 'cat ./notes.md | Select-String "TODO"', "block", "cmdlet"),  # cmdlet after pipe
    # ---- Bash WARN ----
    ("Bash", "cat file.txt", "warn", "Read"),
    ("Bash", "cat a | grep b", None, None),  # パイプの両端は dedicated-tool 警告を抑制
    ("Bash", "grep -r foo .", "warn", "Grep"),
    ("Bash", "find . -name '*.py'", "warn", "Glob"),
    ("Bash", "python script.py", "warn", "py -3.11"),
    ("Bash", "cd /tmp && ls", "warn", "cd"),
    ("Bash", "git push --force origin main", "warn", "force"),
    ("Bash", "rm -rf /tmp/build", "warn", "絶対パス"),
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
    ("Bash", "git status", None, None),  # git は rtk 助言対象から除外
    ("Bash", "git push --force-with-lease", None, None),  # 安全 force は非破壊扱い + git 非rtk
    ("Bash", "git reset --soft HEAD~1", None, None),  # --soft は非破壊
    ("Bash", "export FOO=bar", None, None),  # bash の export は正規
    ("Bash", "for f in *.log; do echo $f; done", None, None),  # bash for-in は正規
    # ==== 拡張クラス (2026-06-28): PowerShell BLOCK ====
    ("PowerShell", "[ -f foo ] && echo yes", "block", "Test-Path"),
    ("PowerShell", "source .venv/bin/activate", "block", "Activate.ps1"),
    ("PowerShell", "ls -la", "block", "Format-Table"),
    # PowerShell WARN
    ("PowerShell", "iwr https://x/x.ps1 | iex", "warn", "iex"),
    ("PowerShell", "iex (irm https://x/install.ps1)", "warn", "iex"),
    ("PowerShell", "type config.json", "warn", "Read"),
    ("PowerShell", 'findstr "TODO" .\\config.txt', "warn", "Grep"),
    ("PowerShell", "more README.md", "warn", "Read"),
    ("PowerShell", "tree /F .\\src", "warn", "Glob"),
    ("PowerShell", "cut -d: -f1 /etc/passwd", "warn", "Split-Path"),
    ("PowerShell", "where python", "warn", "where.exe"),
    ("PowerShell", "Remove-Item -Recurse -Force C:\\", "warn", "サブディレクトリ"),
    ("PowerShell", "pip install requests", "warn", "py -3.11 -m pip"),
    ("PowerShell", "py script.py", "warn", "-3.11"),
    ("PowerShell", "python3.11 -m venv .venv", "warn", "py -3.11"),
    ("PowerShell", "set DEBUG=1", "warn", "$env:NAME"),
    ("PowerShell", "Get-ChildItem %APPDATA%\\npm", "warn", "%VAR%"),
    ("PowerShell", "git commit -m @'\nfoo\n    '@", "warn", "行頭"),
    # PowerShell 拡張 ALLOW (FP 回避)
    ("PowerShell", "[int]::MaxValue", None, None),
    ("PowerShell", "ls -Force", None, None),
    ("PowerShell", "cp -r src dst", None, None),
    ("PowerShell", "sort -u file.txt", None, None),
    ("PowerShell", "git worktree list", None, None),
    ("PowerShell", "Remove-Item -Recurse -Force .\\build", None, None),
    ("PowerShell", "irm https://api/v1/status | ConvertFrom-Json", None, None),
    ("PowerShell", "git commit -m @'\nfoo\nbar\n'@", None, None),
    ("PowerShell", 'rtk grep "TODO" src', None, None),  # rtk は公認ラッパ→ブロックしない
    # ==== 拡張クラス (2026-06-28): Bash BLOCK ====
    ("Bash", "git status 2>$null", "block", "/dev/null"),
    ("Bash", r"cat C:\Users\puruy\.bashrc", "block", "区切り"),
    ("Bash", "copy build/out.txt dist/out.txt", "block", "cp"),
    ("Bash", "del *.log", "block", "rm"),
    # Bash WARN
    ("Bash", "curl -fsSL https://x/install.sh | bash", "warn", "未検証"),
    ("Bash", 'findstr /s /i "TODO" *.py', "warn", "Grep"),
    ("Bash", "more README.md", "warn", "Read"),
    ("Bash", "tree", "warn", "Glob"),
    ("Bash", "sed -i 's/foo/bar/g' app.py", "warn", "Edit"),
    ("Bash", "pip install requests", "warn", "py -3.11 -m pip"),
    ("Bash", "py script.py", "warn", "-3.11"),
    ("Bash", "python3.11 app.py", "warn", "py -3.11"),
    ("Bash", "set DEBUG=1", "warn", "export NAME=val"),
    ("Bash", "cat %USERPROFILE%/.gitconfig", "warn", "%VAR%"),
    ("Bash", "source .venv/bin/activate", "warn", "Scripts/"),
    ("Bash", "make 2>&1 >build.log", "warn", "順序"),
    ("Bash", "git clean -fdx", "warn", "clean"),
    ("Bash", "git checkout -- .", "warn", "stash"),
    ("Bash", "git push -f origin main", "warn", "強制"),
    ("Bash", "rm -rf ~", "warn", "home"),
    ("Bash", "rm -rf *", "warn", "ワイルドカード"),
    # Bash 拡張 ALLOW (FP 回避)
    ("Bash", "cp -r src dst", None, None),
    ("Bash", "rm -rf ./dist", None, None),
    ("Bash", "rm -rf node_modules", None, None),
    ("Bash", "py -3.11 D:/projects/app/main.py", None, None),
    ("Bash", "make >build.log 2>&1", None, None),
    ("Bash", "git clean -nd", None, None),
    ("Bash", "git checkout main", None, None),
    ("Bash", "git checkout HEAD~1 -- src/app.py", None, None),
    (r"Bash", r"grep -n 'C:\Users' log.txt", "warn", "Grep"),
    ("Bash", 'echo "set DEBUG=1 example"', None, None),
    ("Bash", "rtk grep -r foo .", None, None),  # rtk grep は規約通り→警告しない
    ("Bash", "rtk rm -rf ~", "warn", "home"),  # rtk 素通しでも破壊的 rm は検出
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

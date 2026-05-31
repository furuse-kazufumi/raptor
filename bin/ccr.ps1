# ccr.ps1 — Claude Code with auto-Rotation (PowerShell)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$RaptorDir = Split-Path $PSScriptRoot -Parent
Set-Location $RaptorDir
# プロジェクト選択後に投入するのは `/effort ultracode` の 1 行だけにする。
# 再開トリガー(2 行目)は不要 — Claude は起動時に CLAUDE.md / SESSION START を
# 自動で読むため。空文字にすると buildInitialCommands が 2 行目を積まない
# (claude-auto.mjs:325-327)。 (2026-06-01 ユーザー判断)
$env:RAPTOR_AUTO_RESUME_PROMPT = ''
& zx claude-auto.mjs @args

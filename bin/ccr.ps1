# ccr.ps1 — Claude Code with auto-Rotation (PowerShell)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$RaptorDir = Split-Path $PSScriptRoot -Parent
Set-Location $RaptorDir
# 自動入力(effort/再開トリガーの PTY 投入)を無効化し、claude を素のまま起動する=本来の動き。
# effort を上げたい時は起動後に手動で `/effort ultracode` と打つ(実キーボードなので確実)。
# 自動投入を再び有効化するには次行を削除/コメントアウト (2026-06-01 ユーザー判断)。
$env:RAPTOR_AUTO_PTY_DISABLE = '1'
& zx claude-auto.mjs @args

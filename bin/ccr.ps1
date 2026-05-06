# ccr.ps1 — Claude Code with auto-Rotation (PowerShell)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$RaptorDir = Split-Path $PSScriptRoot -Parent
Set-Location $RaptorDir
& zx claude-auto.mjs @args

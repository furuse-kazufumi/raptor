@echo off
:: ccr — Claude Code with auto-Rotation (Windows)
set "RAPTOR_DIR=%~dp0.."
cd /d "%RAPTOR_DIR%"
zx claude-auto.mjs %*

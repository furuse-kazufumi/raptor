@echo off
:: ccr — Claude Code with auto-Rotation (Windows)
set "RAPTOR_DIR=%~dp0.."
cd /d "%RAPTOR_DIR%"
rem 自動入力(effort/再開トリガーの PTY 投入)を無効化=素の claude 起動。再有効化は次行を削除。
set "RAPTOR_AUTO_PTY_DISABLE=1"
zx claude-auto.mjs %*

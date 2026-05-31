@echo off
:: ccr — Claude Code with auto-Rotation (Windows)
set "RAPTOR_DIR=%~dp0.."
cd /d "%RAPTOR_DIR%"
rem 投入は `/effort ultracode` の 1 行だけ。再開トリガー(2 行目)は CLAUDE.md が
rem 起動時に読まれるため不要。空文字で buildInitialCommands が 2 行目を積まない。
set "RAPTOR_AUTO_RESUME_PROMPT="
zx claude-auto.mjs %*

@echo off
:: rp — RAPTOR lightweight project picker (replaces ccr; no PTY, no /effort injection)
:: Runs the PowerShell picker, which writes .raptor-session.json and launches plain claude.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0rp.ps1" %*

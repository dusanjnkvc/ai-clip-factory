@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local-ai.ps1" -Stop
if errorlevel 1 pause

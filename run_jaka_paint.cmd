@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" jaka_paint_app.py
) else (
    python jaka_paint_app.py
)
if errorlevel 1 pause

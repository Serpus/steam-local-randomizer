@echo off
cd /d "%~dp0"

REM Prefer pythonw (no console window), fall back to python.
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" release_gui.py
    exit /b 0
)

where pythonw >nul 2>&1
if %errorlevel% == 0 (
    start "" pythonw release_gui.py
    exit /b 0
)

REM Last resort: regular python (console will flash and stay)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" release_gui.py
) else (
    python release_gui.py
)
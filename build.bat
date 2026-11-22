@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM  Steam Local Randomizer - local build script
REM  Builds both CLI and GUI .exe files into dist\
REM ============================================================

cd /d "%~dp0"

echo.
echo ============================================
echo  Steam Local Randomizer - Build
echo ============================================
echo.

set "DEV_MODE_INSTALLED=0"

REM --- 1. Check/Create venv ----------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Virtual environment not found, creating...

    REM Create venv
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        echo         Make sure Python is installed and in PATH
        goto :fail
    )

    REM Activate
    call .venv\Scripts\activate.bat
    if errorlevel 1 (
        echo [ERROR] Failed to activate virtual environment
        goto :fail
    )

    REM Upgrade pip
    echo [INFO] Upgrading pip...
    python -m pip install --upgrade pip --quiet

    REM Install project in editable mode if pyproject.toml or setup.py exists
    if exist "pyproject.toml" (
        echo [INFO] Found pyproject.toml, installing project in development mode...
        pip install -e ".[dev]" --quiet 2>nul
        if errorlevel 1 (
            echo [INFO] Dev install failed, trying regular install...
            pip install -e . --quiet
        )
        if errorlevel 1 (
            echo [WARN] Failed to install project in dev mode, falling back to requirements...
        ) else (
            set "DEV_MODE_INSTALLED=1"
        )
    ) else if exist "setup.py" (
        echo [INFO] Found setup.py, installing project in development mode...
        pip install -e ".[dev]" --quiet 2>nul
        if errorlevel 1 (
            echo [INFO] Dev install failed, trying regular install...
            pip install -e . --quiet
        )
        if errorlevel 1 (
            echo [WARN] Failed to install project in dev mode, falling back to requirements...
        ) else (
            set "DEV_MODE_INSTALLED=1"
        )
    )

    REM Install requirements if not already done via dev mode
    if "!DEV_MODE_INSTALLED!"=="0" (
        if exist "requirements.txt" (
            echo [INFO] Installing dependencies from requirements.txt...
            pip install -r requirements.txt --quiet
            if errorlevel 1 (
                echo [ERROR] Failed to install requirements.txt
                goto :fail
            )
        ) else (
            echo [WARN] requirements.txt not found
        )
    )

    REM Install dev requirements (pytest etc)
    if exist "requirements-dev.txt" (
        echo [INFO] Installing dev dependencies from requirements-dev.txt...
        pip install -r requirements-dev.txt --quiet
        if errorlevel 1 (
            echo [ERROR] Failed to install requirements-dev.txt
            goto :fail
        )
    ) else (
        echo [INFO] requirements-dev.txt not found, installing pytest...
        pip install pytest --quiet
    )

    REM Install PyInstaller
    echo [INFO] Installing PyInstaller...
    pip install pyinstaller --quiet
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller
        goto :fail
    )

    echo [INFO] Virtual environment setup complete
    echo.

) else (
    REM --- 2. Activate existing venv -------------------------
    call .venv\Scripts\activate.bat
    if errorlevel 1 (
        echo [ERROR] Failed to activate virtual environment
        goto :fail
    )

    REM --- 3. Check PyInstaller ------------------------------
    python -c "import PyInstaller" >nul 2>&1
    if errorlevel 1 (
        echo [INFO] PyInstaller not installed, installing...
        pip install pyinstaller
        if errorlevel 1 (
            echo [ERROR] Failed to install PyInstaller
            goto :fail
        )
    )

    REM --- 3.1 Check pytest ----------------------------------
    python -c "import pytest" >nul 2>&1
    if errorlevel 1 (
        echo [INFO] pytest not installed, installing...
        pip install pytest --quiet
        if errorlevel 1 (
            echo [ERROR] Failed to install pytest
            goto :fail
        )
    )
)

REM --- 4. Tests ----------------------------------------------
echo [0/3] Running tests...

REM Add src to PYTHONPATH so pytest can find the steam_randomizer module
set "PYTHONPATH=src;%PYTHONPATH%"

pytest
if errorlevel 1 (
    echo [ERROR] Tests failed, aborting build
    goto :fail
)

REM Clear PYTHONPATH after tests
set "PYTHONPATH="

REM --- 5. Clean old artifacts --------------------------------
echo [1/3] Cleaning old build artifacts...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
del /q *.spec >nul 2>&1

REM --- 6. Build GUI ------------------------------------------
echo [2/3] Building GUI (steam-randomizer-gui.exe)...
pyinstaller --onefile --windowed --name steam-randomizer-gui --paths src --collect-all vdf --collect-all customtkinter run_gui.py
if errorlevel 1 (
    echo [ERROR] GUI build failed
    goto :fail
)

REM --- 7. Build CLI ------------------------------------------
echo [3/3] Building CLI (steam-randomizer.exe)...
pyinstaller --onefile --console --name steam-randomizer --paths src --collect-all vdf run.py
if errorlevel 1 (
    echo [ERROR] CLI build failed
    goto :fail
)

REM --- 8. Report ---------------------------------------------
echo.
echo ============================================
echo  Build finished successfully
echo ============================================
echo.
echo  dist\steam-randomizer-gui.exe
echo  dist\steam-randomizer.exe
echo.

for %%F in (dist\*.exe) do (
    echo  %%~nxF  -  %%~zF bytes
)

echo.
pause
goto :end

:fail
echo.
echo BUILD FAILED
echo.
pause
exit /b 1

:end
endlocal
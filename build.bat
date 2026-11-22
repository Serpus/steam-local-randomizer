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

REM --- 1. Check venv -----------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\
    echo         Create it with: python -m venv .venv
    goto :fail
)

REM --- 2. Activate venv ---------------------------------------
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment
    goto :fail
)

REM --- 3. Check PyInstaller ----------------------------------
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [INFO] PyInstaller not installed, installing...
    pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller
        goto :fail
    )
)

REM --- 3.1. Tests ----------------------------------
echo [0/4] Running tests...
pytest
if errorlevel 1 (
    echo [ERROR] Tests failed, aborting build
    goto :fail
)

REM --- 4. Clean old artifacts --------------------------------
echo [1/3] Cleaning old build artifacts...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
del /q *.spec >nul 2>&1

REM --- 5. Build GUI ------------------------------------------
echo [2/3] Building GUI (steam-randomizer-gui.exe)...
pyinstaller --onefile --windowed --name steam-randomizer-gui --paths src --collect-all vdf --collect-all customtkinter run_gui.py >nul
if errorlevel 1 (
    echo [ERROR] GUI build failed
    goto :fail
)

REM --- 6. Build CLI ------------------------------------------
echo [3/3] Building CLI (steam-randomizer.exe)...
pyinstaller --onefile --console --name steam-randomizer --paths src --collect-all vdf run.py >nul
if errorlevel 1 (
    echo [ERROR] CLI build failed
    goto :fail
)

REM --- 7. Report ----------------------------------------------
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
goto :end

:fail
echo.
echo BUILD FAILED
echo.
exit /b 1

:end
endlocal
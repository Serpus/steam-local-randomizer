#!/usr/bin/env bash

# Переход в директорию, где лежит скрипт
cd "$(dirname "$0")" || exit 1

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # Без цвета

echo "============================================"
echo " Steam Local Randomizer - Linux Build"
echo "============================================"

fail() {
    echo -e "\n${RED}BUILD FAILED${NC}\n"
    read -p "Press Enter to exit..."
    exit 1
}

# --- 1. Check/Create venv ----------------------------------
if [ ! -f ".venv/bin/python" ]; then
    echo "[INFO] Virtual environment not found, creating..."
    python3 -m venv .venv || fail

    # shellcheck disable=SC1091
    source .venv/bin/activate || fail

    echo "[INFO] Upgrading pip..."
    python -m pip install --upgrade pip --quiet

    DEV_MODE_INSTALLED=0

    if [ -f "pyproject.toml" ]; then
        echo "[INFO] Found pyproject.toml, installing project in development mode..."
        if pip install -e ".[dev]" --quiet 2>/dev/null || pip install -e . --quiet; then
            DEV_MODE_INSTALLED=1
        else
            echo "[WARN] Dev install failed, falling back to requirements..."
        fi
    elif [ -f "setup.py" ]; then
        echo "[INFO] Found setup.py, installing project in development mode..."
        if pip install -e ".[dev]" --quiet 2>/dev/null || pip install -e . --quiet; then
            DEV_MODE_INSTALLED=1
        else
            echo "[WARN] Dev install failed, falling back to requirements..."
        fi
    fi

    if [ "$DEV_MODE_INSTALLED" -eq 0 ]; then
        if [ -f "requirements.txt" ]; then
            echo "[INFO] Installing dependencies from requirements.txt..."
            pip install -r requirements.txt --quiet || fail
        else
            echo "[WARN] requirements.txt not found"
        fi
    fi

    if [ -f "requirements-dev.txt" ]; then
        echo "[INFO] Installing dev dependencies..."
        pip install -r requirements-dev.txt --quiet || fail
    else
        echo "[INFO] requirements-dev.txt not found, installing pytest..."
        pip install pytest --quiet
    fi

    echo "[INFO] Installing PyInstaller..."
    pip install pyinstaller --quiet || fail

    echo "[INFO] Virtual environment setup complete"
    echo ""

else
    # shellcheck disable=SC1091
    source .venv/bin/activate || fail

    if ! python -c "import PyInstaller" 2>/dev/null; then
        echo "[INFO] PyInstaller not installed, installing..."
        pip install pyinstaller || fail
    fi

    if ! python -c "import pytest" 2>/dev/null; then
        echo "[INFO] pytest not installed, installing..."
        pip install pytest --quiet || fail
    fi
fi

# --- 4. Tests ----------------------------------------------
echo "[0/3] Running tests..."
export PYTHONPATH="src:${PYTHONPATH:-}"

if ! pytest; then
    echo "[ERROR] Tests failed, aborting build"
    fail
fi

unset PYTHONPATH

# --- 5. Clean old artifacts --------------------------------
echo "[1/3] Cleaning old build artifacts..."
rm -rf build dist
rm -f *.spec

# --- 6. Build GUI ------------------------------------------
echo "[2/3] Building GUI (steam-randomizer-gui)..."
# В Linux --windowed работает, но требует наличия X11/Wayland библиотек в системе
pyinstaller --onefile --windowed --name steam-randomizer-gui --paths src --collect-all vdf --collect-all customtkinter run_gui.py || fail

# --- 7. Build CLI ------------------------------------------
echo "[3/3] Building CLI (steam-randomizer)..."
pyinstaller --onefile --console --name steam-randomizer --paths src --collect-all vdf run.py || fail

# --- 8. Report ---------------------------------------------
echo ""
echo "============================================"
echo -e " ${GREEN}Build finished successfully${NC}"
echo "============================================"
echo ""
echo " dist/steam-randomizer-gui"
echo " dist/steam-randomizer"
echo ""

# Вывод размеров файлов (универсальный для Linux и macOS)
for file in dist/*; do
    if [ -f "$file" ]; then
        filename=$(basename "$file")
        if stat -c%s "$file" >/dev/null 2>&1; then
            size=$(stat -c%s "$file") # GNU stat (Linux)
        else
            size=$(stat -f%z "$file") # BSD stat (macOS)
        fi
        echo " $filename  -  $size bytes"
    fi
done

echo ""
echo "Чтобы запустить GUI, выполните в терминале:"
echo "  ./dist/steam-randomizer-gui"
echo ""
read -p "Press Enter to exit..."
"""Locate the Steam installation on Windows."""
from __future__ import annotations

import winreg
from pathlib import Path


class SteamNotFoundError(Exception):
    """Raised when Steam cannot be located on the system."""


# Fallback paths if the registry key is missing.
_FALLBACK_PATHS = (
    Path(r"C:\Program Files (x86)\Steam"),
    Path(r"C:\Program Files\Steam"),
)


def find_steam_path() -> Path:
    """Return the Steam root directory.

    Reads `SteamPath` from the Windows registry. Falls back to common
    install locations if the registry key is absent.

    Raises:
        SteamNotFoundError: if no valid Steam installation is found.
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
            candidate = Path(steam_path)
            if candidate.is_dir():
                return candidate
    except FileNotFoundError:
        pass
    except OSError:
        pass

    for fallback in _FALLBACK_PATHS:
        if fallback.is_dir():
            return fallback

    raise SteamNotFoundError(
        "Steam installation not found. Make sure Steam is installed."
    )
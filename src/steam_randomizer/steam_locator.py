"""Locate the Steam installation (Windows / Linux / SteamOS)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

class SteamNotFoundError(Exception):
    """Raised when Steam cannot be located on the system."""

def find_steam_path() -> Path:
    """Return the Steam root directory.

    Windows:
      Reads `SteamPath` from the registry. Falls back to common install locations.

    Linux / SteamOS:
      Checks standard locations in this order:
        1. ~/.steam/steam (symlink to actual install)
        2. ~/.local/share/Steam
        3. ~/.var/app/com.valvesoftware.Steam/.steam/steam (Flatpak)
        4. /usr/share/steam (system-wide)

    Raises:
        SteamNotFoundError: if no valid Steam installation is found.
    """
    if sys.platform == "win32":
        return _find_steam_windows()
    else:
        return _find_steam_linux()

def _find_steam_windows() -> Path:
    """Windows-specific Steam detection using registry."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
            candidate = Path(steam_path)
            if candidate.is_dir():
                return candidate
    except ImportError:
        pass
    except FileNotFoundError:
        pass
    except OSError:
        pass

    # Fallback paths for Windows
    fallbacks = (
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
    )
    for fallback in fallbacks:
        if fallback.is_dir():
            return fallback

    raise SteamNotFoundError(
        "Steam installation not found. Make sure Steam is installed."
    )

def _find_steam_linux() -> Path:
    """Linux-specific Steam detection using standard paths."""
    home = Path.home()

    # List of standard Steam locations on Linux (in order of preference)
    candidates = [
        home / ".steam" / "steam",  # Symlink to actual install (most common)
        home / ".steam" / "root",   # Alternative symlink target
        home / ".local" / "share" / "Steam",  # Standard XDG location
        home / ".var" / "app" / "com.valvesoftware.Steam" / ".steam" / "steam",  # Flatpak
        home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",  # Flatpak alternative
        Path("/usr/share/steam"),  # System-wide (Arch, some distros)
        Path("/opt/steam"),  # Some manual installations
    ]

    # Also check XDG_DATA_HOME if set
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        candidates.insert(2, Path(xdg_data) / "Steam")

    for candidate in candidates:
        try:
            # Resolve symlinks safely
            resolved = candidate.resolve(strict=False)

            # Check if it's a valid directory
            if not resolved.is_dir():
                continue

            # Check if steamapps exists (validates it's actually Steam)
            # Steam uses both lowercase and capitalized versions
            steamapps = resolved / "steamapps"
            steamapps_alt = resolved / "SteamApps"

            if steamapps.is_dir() or steamapps_alt.is_dir():
                return resolved
        except (OSError, PermissionError):
            # Skip paths we can't access
            continue

    raise SteamNotFoundError(
        "Steam installation not found. Install Steam from your package manager "
        "or from https://store.steampowered.com/about/"
    )
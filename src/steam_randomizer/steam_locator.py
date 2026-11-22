"""Locate the Steam installation (Windows / Linux / SteamOS)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

class SteamNotFoundError(Exception):
    """Raised when Steam cannot be located on the system."""

# Fallback paths for Windows
_FALLBACK_PATHS_WINDOWS = (
    Path(r"C:\Program Files (x86)\Steam"),
    Path(r"C:\Program Files\Steam"),
)

# Fallback paths for Linux
_LINUX_FALLBACK_PATHS = (
    Path.home() / ".steam" / "steam",  # Symlink to actual install (most common)
    Path.home() / ".steam" / "root",   # Alternative symlink target
    Path.home() / ".local" / "share" / "Steam",  # Standard XDG location
    Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".steam" / "steam",  # Flatpak
    Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",  # Flatpak alternative
    Path("/usr/share/steam"),  # System-wide (Arch, some distros)
    Path("/opt/steam"),  # Some manual installations
)

def _looks_like_steam(candidate: Path) -> bool:
    """Check if a directory looks like a valid Steam installation.

    Returns True if the directory contains steamapps or SteamApps folder.
    """
    if not candidate.is_dir():
        return False
    steamapps = candidate / "steamapps"
    steamapps_alt = candidate / "SteamApps"
    return steamapps.is_dir() or steamapps_alt.is_dir()

def find_steam_path() -> Path:
    """Return the Steam root directory.

    Supports environment variable override: STEAM_PATH

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
    # Environment variable override (useful for testing and custom setups)
    env_steam = os.environ.get("STEAM_PATH")
    if env_steam:
        env_path = Path(env_steam)
        if env_path.is_dir():
            return env_path

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
    for fallback in _FALLBACK_PATHS_WINDOWS:
        if fallback.is_dir():
            return fallback

    raise SteamNotFoundError(
        "Steam installation not found. Make sure Steam is installed."
    )

def _find_steam_linux() -> Path:
    """Linux-specific Steam detection using standard paths."""
    # Check XDG_DATA_HOME if set
    xdg_data = os.environ.get("XDG_DATA_HOME")
    candidates = list(_LINUX_FALLBACK_PATHS)

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
            if _looks_like_steam(resolved):
                return resolved
        except (OSError, PermissionError):
            # Skip paths we can't access
            continue

    raise SteamNotFoundError(
        "Steam installation not found. Install Steam from your package manager "
        "or from https://store.steampowered.com/about/"
    )
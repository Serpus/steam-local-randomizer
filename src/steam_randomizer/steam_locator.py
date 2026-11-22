"""Locate the Steam installation on Windows, Linux and SteamOS (Steam Deck)."""
from __future__ import annotations

import os
import sys
from pathlib import Path


class SteamNotFoundError(Exception):
    """Raised when Steam cannot be located on the system."""


# Fallback paths if the registry key is missing (Windows).
_FALLBACK_PATHS = (
    Path(r"C:\Program Files (x86)\Steam"),
    Path(r"C:\Program Files\Steam"),
)

# Common native-Linux install locations, including Flatpak and Steam Deck.
_LINUX_FALLBACK_PATHS = (
    Path.home() / ".steam" / "root",          # modern Ubuntu/Fedora/Deck layout
    Path.home() / ".local" / "share" / "Steam",  # older ~/.steam symlink target
    Path.home() / ".steam" / "steam",         # legacy symlink layout
    Path("/home/deck/.local/share/Steam"),    # Steam Deck (if run as another user)
    Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / "data" / ".steam" / "root",
    Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".steam" / "root",
    Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / "data" / ".local" / "share" / "Steam",
    Path("/var/lib/flatpak/app/com.valvesoftware.Steam/current/active/files/data/.steam/root"),
)


def _find_steam_path_windows() -> Path:
    """Windows: read ``SteamPath`` from the registry, fall back to defaults."""
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

    for fallback in _FALLBACK_PATHS:
        if fallback.is_dir():
            return fallback

    raise SteamNotFoundError(
        "Steam installation not found. Make sure Steam is installed."
    )


def _looks_like_steam(path: Path) -> bool:
    """Heuristic check that *path* is a real Steam root directory."""
    if not path.is_dir():
        return False
    if (path / "steamapps").is_dir():
        return True
    if (path / "steam.exe").is_file() or (path / "ubuntu12_64" / "steam").is_file():
        return True
    if (path / "libraryfolders.vdf").is_file():
        return True
    if (path / "config" / "libraryfolders.vdf").is_file():
        return True
    return False


def _find_steam_path_linux() -> Path:
    """Linux / SteamOS: check env override and common install locations.

    Resolution order:
      1. ``STEAM_PATH`` environment variable (handy for custom mounts).
      2. ``~/.steam/root`` and other well-known directories.
      3. ``~/.steam/sdk64/steam.cfg``-style markers are ignored; instead we
         look for any ``.steam*`` folder in $HOME containing ``steamapps``.
    """
    env_path = os.environ.get("STEAM_PATH")
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.is_dir():
            return candidate

    checked: set[Path] = set()
    for fallback in _LINUX_FALLBACK_PATHS:
        if fallback in checked:
            continue
        checked.add(fallback)
        if _looks_like_steam(fallback):
            return fallback

    # Last resort: scan the home directory for hidden .steam* folders.
    try:
        home = Path.home()
        for entry in sorted(home.glob(".steam*")):
            resolved = entry.resolve()
            if resolved in checked:
                continue
            checked.add(resolved)
            if _looks_like_steam(entry):
                return entry
    except OSError:
        pass

    raise SteamNotFoundError(
        "Steam installation not found. Make sure Steam is installed.\n"
        "You can also set the STEAM_PATH environment variable to your "
        "Steam folder (e.g. ~/.steam/root or the Flatpak data dir)."
    )


def find_steam_path() -> Path:
    """Return the Steam root directory on the current platform.

    Raises:
        SteamNotFoundError: if no valid Steam installation is found.
    """
    if sys.platform == "win32":
        return _find_steam_path_windows()
    if sys.platform == "darwin":
        candidate = Path.home() / "Library" / "Application Support" / "Steam"
        if _looks_like_steam(candidate):
            return candidate
        raise SteamNotFoundError("Steam installation not found.")
    return _find_steam_path_linux()

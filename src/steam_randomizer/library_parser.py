"""Parse Steam library metadata (libraryfolders.vdf + appmanifest_*.acf)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import vdf


@dataclass(frozen=True)
class Game:
    """A game installed in one of the Steam libraries."""

    appid: str
    name: str
    installdir: str
    library_path: Path


def get_library_paths(steam_path: Path) -> list[Path]:
    """Return all Steam library root folders (including extra drives)."""
    vdf_path = steam_path / "steamapps" / "libraryfolders.vdf"
    if not vdf_path.is_file():
        return [steam_path]

    with vdf_path.open("r", encoding="utf-8") as f:
        data = vdf.load(f)

    libraries: list[Path] = []
    folders = data.get("libraryfolders", {})
    if isinstance(folders, dict):
        for value in folders.values():
            if not isinstance(value, dict):
                continue
            path_str = value.get("path")
            if not path_str:
                continue
            candidate = Path(path_str)
            if candidate.is_dir():
                libraries.append(candidate)

    # Always include the main Steam folder as a safety net.
    if steam_path not in libraries:
        libraries.insert(0, steam_path)
    return libraries


def _parse_acf(acf_path: Path) -> dict:
    with acf_path.open("r", encoding="utf-8") as f:
        return vdf.load(f)


def scan_library(library_path: Path) -> list[Game]:
    """Scan a single library folder and return installed games."""
    steamapps = library_path / "steamapps"
    if not steamapps.is_dir():
        return []

    games: list[Game] = []
    for manifest in steamapps.glob("appmanifest_*.acf"):
        try:
            data = _parse_acf(manifest)
        except (OSError, SyntaxError):
            continue
        state = data.get("AppState", {})
        if not isinstance(state, dict):
            continue
        appid = str(state.get("appid", "")).strip()
        name = str(state.get("name", "")).strip()
        installdir = str(state.get("installdir", "")).strip()
        if appid and name:
            games.append(
                Game(
                    appid=appid,
                    name=name,
                    installdir=installdir,
                    library_path=library_path,
                )
            )
    return games


def find_installed_games(steam_path: Path) -> list[Game]:
    """Scan all Steam libraries and return every installed game entry."""
    all_games: list[Game] = []
    seen: set[str] = set()
    for library in get_library_paths(steam_path):
        for game in scan_library(library):
            if game.appid not in seen:
                seen.add(game.appid)
                all_games.append(game)
    return all_games
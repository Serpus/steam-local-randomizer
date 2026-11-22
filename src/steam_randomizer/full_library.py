"""Load the user's full Steam library (installed + uninstalled)."""
from __future__ import annotations

from pathlib import Path

import vdf

from .app_names import resolve_names
from .library_parser import Game, find_installed_games
from .randomizer import is_playable_game


NON_GAME_TYPES: frozenset[str] = frozenset({
    "dlc", "music", "tool", "application", "video",
    "series", "hardware", "advertising", "config", "beta",
})


def _find_latest_userdata(steam_path: Path) -> Path | None:
    userdata = steam_path / "userdata"
    if not userdata.is_dir():
        return None
    candidates = []
    for entry in userdata.iterdir():
        if not entry.is_dir():
            continue
        config = entry / "config"
        localconfig = config / "localconfig.vdf"
        if localconfig.is_file():
            candidates.append((localconfig.stat().st_mtime, config))
    if not candidates:
        return None
    return max(candidates, key=lambda x: x[0])[1]


def _load_owned_appids(config_dir: Path) -> set[str]:
    localconfig = config_dir / "localconfig.vdf"
    if not localconfig.is_file():
        return set()
    with localconfig.open("r", encoding="utf-8") as f:
        data = vdf.load(f)
    steam_node = (
        data.get("UserLocalConfigStore", {})
        .get("Software", {})
        .get("Valve", {})
        .get("Steam", {})
    )
    apps = steam_node.get("apps") or steam_node.get("Apps") or {}
    if not isinstance(apps, dict):
        return set()
    return {str(k) for k in apps.keys() if str(k).isdigit()}


def find_all_owned_games(steam_path: Path) -> list[Game]:
    """Every game the user owns, with real names when available."""
    config_dir = _find_latest_userdata(steam_path)
    if config_dir is None:
        return []

    owned = _load_owned_appids(config_dir)
    if not owned:
        return []

    infos = resolve_names(steam_path, owned)
    installed = {g.appid: g for g in find_installed_games(steam_path)}

    games: list[Game] = []
    for appid in owned:
        info = infos.get(appid)
        if info and info.type in NON_GAME_TYPES:
            continue

        game = installed.get(appid) or Game(
            appid=appid,
            name=info.name if info else f"App {appid}",
            installdir="",
            library_path=steam_path,
        )
        if is_playable_game(game):
            games.append(game)

    games.sort(key=lambda g: g.name.casefold())
    return games
r"""Persistent user settings (theme, filters, etc).

Location:
  * Windows: %APPDATA%\steam-local-randomizer\settings.json
  * Linux / SteamOS: $XDG_CONFIG_HOME/steam-local-randomizer/settings.json
    (defaults to ~/.config/steam-local-randomizer/)
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

_SETTINGS_FILENAME = "settings.json"

DEFAULTS: dict = {
    "use_blacklist": True,     # учитывать чёрный список при выборе
    "blacklist": [],           # список appid, которые никогда не должны выпадать
}


def config_dir() -> Path | None:
    """Platform-appropriate per-user config directory."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if not base:
            return None
        return Path(base) / "steam-local-randomizer"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "steam-local-randomizer"
    return Path.home() / ".config" / "steam-local-randomizer"


def _settings_path() -> Path | None:
    base = config_dir()
    if base is None:
        return None
    return base / _SETTINGS_FILENAME


def load_settings() -> dict:
    """Load settings merged with defaults. Never raises."""
    path = _settings_path()
    if path is None or not path.is_file():
        return copy.deepcopy(DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return copy.deepcopy(DEFAULTS)
    if not isinstance(data, dict):
        return copy.deepcopy(DEFAULTS)
    merged = copy.deepcopy(DEFAULTS)
    merged.update(data)
    return merged


def _backup_if_unreadable(path: Path) -> None:
    """Скопировать битый settings.json в `.corrupt`, чтобы запись его не стёрла."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return
    try:
        json.loads(raw)
    except ValueError:
        try:
            path.with_name(path.name + ".corrupt").write_text(raw, encoding="utf-8")
        except OSError:
            pass


def save_settings(settings: dict) -> None:
    """Write settings to disk atomically. Never raises."""
    path = _settings_path()
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _backup_if_unreadable(path)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, path)
    except OSError:
        pass


# ---- Чёрный список ----------------------------------------------------

def get_blacklist() -> set[str]:
    """Текущий чёрный список как множество appid."""
    s = load_settings()
    return set(str(a) for a in s.get("blacklist", []))


def is_blacklisted(appid: str) -> bool:
    return str(appid) in get_blacklist()


def toggle_blacklist(appid: str) -> bool:
    """Добавить/удалить из чёрного списка. Возвращает, в списке ли игра сейчас."""
    s = load_settings()
    bl = set(str(a) for a in s.get("blacklist", []))
    appid = str(appid)
    if appid in bl:
        bl.discard(appid)
    else:
        bl.add(appid)
    s["blacklist"] = sorted(bl)
    save_settings(s)
    return appid in bl


def clear_blacklist() -> None:
    """Полностью очистить чёрный список."""
    s = load_settings()
    s["blacklist"] = []
    save_settings(s)


def is_use_blacklist() -> bool:
    """Учитывается ли чёрный список при выборе."""
    return bool(load_settings().get("use_blacklist", True))


def set_use_blacklist(enabled: bool) -> None:
    s = load_settings()
    s["use_blacklist"] = bool(enabled)
    save_settings(s)
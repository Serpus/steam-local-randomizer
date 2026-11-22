"""Persistent user settings (theme, filters, etc).

Location: %APPDATA%\\steam-local-randomizer\\settings.json
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_SETTINGS_FILENAME = "settings.json"

DEFAULTS: dict = {
    "theme": "dark",  # "dark" | "light"
}


def _settings_path() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "steam-local-randomizer" / _SETTINGS_FILENAME


def load_settings() -> dict:
    """Load settings merged with defaults. Never raises."""
    path = _settings_path()
    if path is None or not path.is_file():
        return dict(DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULTS)
    if not isinstance(data, dict):
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    merged.update(data)
    return merged


def save_settings(settings: dict) -> None:
    """Write settings to disk. Never raises."""
    path = _settings_path()
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass
"""Tests for settings module."""
from __future__ import annotations

import pytest

from steam_randomizer import settings as settings_mod


@pytest.fixture(autouse=True)
def tmp_appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    yield tmp_path


def test_load_defaults_when_no_file():
    s = settings_mod.load_settings()
    assert s == settings_mod.DEFAULTS


def test_save_and_load_roundtrip():
    settings_mod.save_settings({"theme": "light"})
    s = settings_mod.load_settings()
    assert s["theme"] == "light"


def test_load_corrupt_returns_defaults(tmp_path):
    f = tmp_path / "steam-local-randomizer" / "settings.json"
    f.parent.mkdir(parents=True)
    f.write_text("not json {{{", encoding="utf-8")
    assert settings_mod.load_settings() == settings_mod.DEFAULTS


def test_partial_settings_merged_with_defaults():
    settings_mod.save_settings({"theme": "light"})
    # Simulate a file written by an older version (no "theme" key)
    (tmp_path := settings_mod._settings_path()).write_text(
        '{"some_future_key": 42}', encoding="utf-8"
    )
    s = settings_mod.load_settings()
    assert s["some_future_key"] == 42
    assert s["theme"] == "dark"  # from DEFAULTS
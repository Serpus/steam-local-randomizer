"""Tests for settings module."""
from __future__ import annotations

import json

import pytest

from steam_randomizer import settings as settings_mod


@pytest.fixture(autouse=True)
def tmp_appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    yield tmp_path


def test_load_defaults_when_no_file():
    s = settings_mod.load_settings()
    assert s == settings_mod.DEFAULTS


def test_save_and_load_roundtrip():
    settings_mod.save_settings({"use_blacklist": False})
    s = settings_mod.load_settings()
    assert s["use_blacklist"] is False


def test_load_corrupt_returns_defaults(tmp_path):
    f = tmp_path / "steam-local-randomizer" / "settings.json"
    f.parent.mkdir(parents=True)
    f.write_text("not json {{{", encoding="utf-8")
    assert settings_mod.load_settings() == settings_mod.DEFAULTS


def test_corrupt_file_backed_up_before_save(tmp_path):
    f = tmp_path / "steam-local-randomizer" / "settings.json"
    f.parent.mkdir(parents=True)
    f.write_text("not json {{{", encoding="utf-8")

    settings_mod.save_settings({"blacklist": ["10"]})

    assert json.loads(f.read_text(encoding="utf-8"))["blacklist"] == ["10"]
    assert (f.parent / "settings.json.corrupt").read_text(encoding="utf-8") == "not json {{{"


def test_partial_settings_merged_with_defaults():
    settings_mod.save_settings({"use_blacklist": False})
    # Simulate a file written by an older version (no "use_blacklist" key)
    settings_mod._settings_path().write_text(
        '{"some_future_key": 42}', encoding="utf-8"
    )
    s = settings_mod.load_settings()
    assert s["some_future_key"] == 42
    assert s["use_blacklist"] is True  # from DEFAULTS
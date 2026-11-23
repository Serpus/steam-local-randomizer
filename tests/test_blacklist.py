"""Tests for blacklist helpers in settings module."""
from __future__ import annotations

import pytest

from steam_randomizer import settings


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))


def test_default_blacklist_is_empty():
    assert settings.get_blacklist() == set()
    assert settings.is_use_blacklist() is True


def test_toggle_adds_and_removes():
    assert settings.is_blacklisted("440") is False
    in_list = settings.toggle_blacklist("440")
    assert in_list is True
    assert settings.is_blacklisted("440") is True
    in_list = settings.toggle_blacklist("440")
    assert in_list is False
    assert settings.is_blacklisted("440") is False


def test_blacklist_persists_across_loads():
    settings.toggle_blacklist("10")
    settings.toggle_blacklist("20")
    bl = settings.get_blacklist()
    assert bl == {"10", "20"}


def test_clear_blacklist():
    settings.toggle_blacklist("10")
    settings.toggle_blacklist("20")
    settings.clear_blacklist()
    assert settings.get_blacklist() == set()


def test_use_blacklist_flag():
    assert settings.is_use_blacklist() is True
    settings.set_use_blacklist(False)
    assert settings.is_use_blacklist() is False
    settings.set_use_blacklist(True)
    assert settings.is_use_blacklist() is True
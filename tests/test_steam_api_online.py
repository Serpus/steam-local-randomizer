"""Offline tests for steam_api.last_fetch_online() flag."""
from __future__ import annotations

import json
import urllib.error

import pytest

from steam_randomizer import steam_api


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    steam_api.reset_for_testing()
    yield
    steam_api.reset_for_testing()


class _Resp:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_online_flag_set_on_success(monkeypatch):
    payload = {"response": {"store_items": [{"appid": 440, "name": "Team Fortress 2"}]}}
    monkeypatch.setattr(
        steam_api.urllib.request, "urlopen", lambda req, timeout=None: _Resp(payload)
    )
    assert steam_api.last_fetch_online() is False
    names = steam_api.get_app_details(["440"])
    assert names == {"440": "Team Fortress 2"}
    assert steam_api.last_fetch_online() is True


def test_online_flag_stays_false_on_network_error(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(steam_api.urllib.request, "urlopen", boom)
    assert steam_api.get_app_details(["570"]) == {}
    assert steam_api.last_fetch_online() is False


def test_empty_items_still_counts_as_online(monkeypatch):
    monkeypatch.setattr(
        steam_api.urllib.request,
        "urlopen",
        lambda req, timeout=None: _Resp({"response": {"store_items": []}}),
    )
    assert steam_api.get_app_details(["999"]) == {}
    assert steam_api.last_fetch_online() is True
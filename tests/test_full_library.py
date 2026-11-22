"""Tests for full-library loading."""
from __future__ import annotations

import os
import time

import vdf

from steam_randomizer.full_library import (
    _find_latest_userdata,
    _load_owned_appids,
    find_all_owned_games,
)


def _make_localconfig(appids: list[str]) -> str:
    data = {
        "UserLocalConfigStore": {
            "Software": {
                "Valve": {
                    "Steam": {
                        "apps": {appid: {"LaunchOptions": ""} for appid in appids}
                    }
                }
            }
        }
    }
    return vdf.dumps(data)


def test_load_owned_appids(tmp_path):
    config = tmp_path / "userdata" / "123" / "config"
    config.mkdir(parents=True)
    (config / "localconfig.vdf").write_text(
        _make_localconfig(["1145360", "1091500"]), encoding="utf-8"
    )
    assert _load_owned_appids(config) == {"1145360", "1091500"}


def test_load_owned_appids_legacy_key(tmp_path):
    """Old Steam used 'Apps' (capital A)."""
    config = tmp_path / "userdata" / "123" / "config"
    config.mkdir(parents=True)
    data = {
        "UserLocalConfigStore": {
            "Software": {"Valve": {"Steam": {"Apps": {"1145360": {}}}}}
        }
    }
    (config / "localconfig.vdf").write_text(vdf.dumps(data), encoding="utf-8")
    assert _load_owned_appids(config) == {"1145360"}


def test_load_owned_appids_missing(tmp_path):
    assert _load_owned_appids(tmp_path) == set()


def test_find_latest_userdata_picks_newest(tmp_path):
    userdata = tmp_path / "userdata"
    old = userdata / "111" / "config"
    new = userdata / "222" / "config"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    (old / "localconfig.vdf").write_text(_make_localconfig([]), encoding="utf-8")
    (new / "localconfig.vdf").write_text(_make_localconfig([]), encoding="utf-8")
    old_time = time.time() - 100
    os.utime(old / "localconfig.vdf", (old_time, old_time))
    assert _find_latest_userdata(tmp_path) == new


def test_find_latest_userdata_none(tmp_path):
    assert _find_latest_userdata(tmp_path) is None


def test_find_all_owned_games_no_files(tmp_path):
    assert find_all_owned_games(tmp_path) == []
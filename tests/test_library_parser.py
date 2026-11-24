"""Tests for Steam library discovery and ACF parsing."""
from __future__ import annotations

import vdf

from steam_randomizer.library_parser import (
    find_installed_games,
    get_library_paths,
    scan_library,
)


def _write_vdf(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(vdf.dumps(data), encoding="utf-8")


def test_get_library_paths_with_vdf(tmp_path):
    steam = tmp_path / "Steam"
    extra = tmp_path / "ExtraLibrary"
    (steam / "steamapps").mkdir(parents=True)
    (extra / "steamapps").mkdir(parents=True)

    _write_vdf(
        steam / "steamapps" / "libraryfolders.vdf",
        {
            "libraryfolders": {
                "0": {"path": str(steam)},
                "1": {"path": str(extra)},
            }
        },
    )

    paths = get_library_paths(steam)
    assert steam in paths
    assert extra in paths


def test_get_library_paths_without_vdf_falls_back(tmp_path):
    steam = tmp_path / "Steam"
    steam.mkdir()
    assert get_library_paths(steam) == [steam]


def test_scan_library_reads_acf(tmp_path):
    steam = tmp_path / "Steam"
    _write_vdf(
        steam / "steamapps" / "appmanifest_1145360.acf",
        {
            "AppState": {
                "appid": "1145360",
                "name": "Hades",
                "installdir": "Hades",
            }
        },
    )

    games = scan_library(steam)
    assert len(games) == 1
    assert games[0].appid == "1145360"
    assert games[0].name == "Hades"
    assert games[0].installdir == "Hades"
    assert games[0].library_path == steam


def test_scan_library_skips_malformed_acf(tmp_path):
    steam = tmp_path / "Steam"
    bad = steam / "steamapps" / "appmanifest_broken.acf"
    bad.parent.mkdir(parents=True)
    bad.write_text("not a valid vdf {{{", encoding="utf-8")

    # Malformed files should not raise, just be skipped.
    assert scan_library(steam) == []


def test_scan_library_nonexistent_path_returns_empty(tmp_path):
    assert scan_library(tmp_path / "does-not-exist") == []


def test_find_installed_games_aggregates_libraries(tmp_path):
    steam = tmp_path / "Steam"
    extra = tmp_path / "ExtraLibrary"

    _write_vdf(
        steam / "steamapps" / "libraryfolders.vdf",
        {
            "libraryfolders": {
                "0": {"path": str(steam)},
                "1": {"path": str(extra)},
            }
        },
    )
    _write_vdf(
        steam / "steamapps" / "appmanifest_1.acf",
        {"AppState": {"appid": "1", "name": "Game A", "installdir": "GameA"}},
    )
    _write_vdf(
        extra / "steamapps" / "appmanifest_2.acf",
        {"AppState": {"appid": "2", "name": "Game B", "installdir": "GameB"}},
    )

    games = find_installed_games(steam)
    names = {g.name for g in games}
    assert names == {"Game A", "Game B"}


def test_find_installed_games_deduplicates_appid(tmp_path):
    steam = tmp_path / "Steam"
    extra = tmp_path / "ExtraLibrary"
    _write_vdf(
        steam / "steamapps" / "libraryfolders.vdf",
        {
            "libraryfolders": {
                "0": {"path": str(steam)},
                "1": {"path": str(extra)},
            }
        },
    )
    for lib in (steam, extra):
        _write_vdf(
            lib / "steamapps" / "appmanifest_5.acf",
            {"AppState": {"appid": "5", "name": "Dup", "installdir": "Dup"}},
        )

    games = find_installed_games(steam)
    assert [g.appid for g in games] == ["5"]
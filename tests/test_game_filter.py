"""Tests for hiding unnamed demo/delisted games from the full library."""
from __future__ import annotations

from pathlib import Path

from steam_randomizer.game_filter import hide_unnamed_games, is_placeholder_name
from steam_randomizer.library_parser import Game


def _g(appid: str, name: str) -> Game:
    return Game(appid=appid, name=name, installdir="", library_path=Path("/x"))


def test_placeholder_variants():
    assert is_placeholder_name("440", "App 440")
    assert is_placeholder_name("440", "app #440")
    assert is_placeholder_name("440", "App <440>")
    assert is_placeholder_name("440", "440")
    assert not is_placeholder_name("440", "Team Fortress 2")
    assert not is_placeholder_name("440", "App 441")
    assert not is_placeholder_name("440", "Half-Life Demo")  # именованное демо остаётся


def test_offline_keeps_everything():
    games = [_g("1", "App 1"), _g("2", "Hades")]
    assert hide_unnamed_games(games, online=False) == games


def test_online_hides_unnamed():
    games = [_g("1", "App 1"), _g("2", "Hades"), _g("3", "App 3")]
    out = hide_unnamed_games(games, online=True)
    assert [g.appid for g in out] == ["2"]


def test_online_but_nothing_named_keeps_all():
    games = [_g("1", "App 1"), _g("2", "App 2")]
    assert hide_unnamed_games(games, online=True) == games


def test_empty_list():
    assert hide_unnamed_games([], online=True) == []
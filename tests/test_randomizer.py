"""Tests for the filter/pick logic."""
from __future__ import annotations

import random

from steam_randomizer.randomizer import filter_games, is_playable_game, pick_random_game


def test_filter_excludes_known_tools_by_appid(make_game):
    games = [
        make_game("228980", "Steamworks Common Redistributables"),
        make_game("1145360", "Hades"),
    ]
    assert [g.name for g in filter_games(games)] == ["Hades"]


def test_filter_excludes_by_name_keyword(make_game):
    games = [
        make_game("999", "Proton 8.0"),
        make_game("888", "Steam Linux Runtime 3.0"),
        make_game("1145360", "Hades"),
    ]
    assert [g.name for g in filter_games(games)] == ["Hades"]


def test_filter_keeps_regular_games(make_game):
    games = [
        make_game("1145360", "Hades"),
        make_game("1091500", "Cyberpunk 2077"),
    ]
    assert len(filter_games(games)) == 2


def test_is_playable_game_positive(make_game):
    assert is_playable_game(make_game("1145360", "Hades"))


def test_is_playable_game_negative(make_game):
    assert not is_playable_game(make_game("228980", "Steamworks Common Redistributables"))


def test_pick_random_game_empty_returns_none():
    assert pick_random_game([]) is None


def test_pick_random_game_returns_member(make_game):
    games = [make_game("1", "A"), make_game("2", "B"), make_game("3", "C")]
    rng = random.Random(42)
    picked = pick_random_game(games, rng)
    assert picked in games


def test_pick_random_game_deterministic_with_seed(make_game):
    games = [make_game(str(i), f"Game {i}") for i in range(10)]
    a = pick_random_game(games, random.Random(123))
    b = pick_random_game(games, random.Random(123))
    assert a == b

def test_filter_excludes_wallpaper_engine(make_game):
    games = [
        make_game("431960", "Wallpaper Engine"),
        make_game("1145360", "Hades"),
    ]
    assert [g.name for g in filter_games(games)] == ["Hades"]
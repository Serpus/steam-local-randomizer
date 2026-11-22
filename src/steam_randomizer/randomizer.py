"""Logic for filtering library entries and picking a random game."""
from __future__ import annotations

import random

from .library_parser import Game


# Non-game entries that Steam installs alongside real games.
EXCLUDED_APPIDS: frozenset[str] = frozenset(
    {
        "228980",   # Steamworks Common Redistributables
        "1070560",  # Steam Linux Runtime 1.0
        "1391110",  # Steam Linux Runtime 2.0 (soldier)
        "1628350",  # Steam Linux Runtime 3.0 (sniper)
        "1493710",  # Proton Experimental
        "858280",   # Proton 5.13
        "961940",   # Proton 5.13 (alt)
        "1054830",  # Proton 6.3
        "1887720",  # Proton 7.0
        "2348590",  # Proton 8.0
        "2805730",  # Proton 9.0
        "250820",   # SteamVR
    }
)

EXCLUDED_NAME_KEYWORDS: tuple[str, ...] = (
    "proton",
    "steamworks common",
    "steam linux runtime",
    "steamvr",
)


def is_playable_game(game: Game) -> bool:
    """Return True if the entry looks like an actual playable game."""
    if game.appid in EXCLUDED_APPIDS:
        return False
    name_lower = game.name.lower()
    return not any(keyword in name_lower for keyword in EXCLUDED_NAME_KEYWORDS)


def filter_games(games: list[Game]) -> list[Game]:
    """Drop non-game entries from the given list."""
    return [g for g in games if is_playable_game(g)]


def pick_random_game(games: list[Game], rng: random.Random | None = None) -> Game | None:
    """Return a random game from the given pool, or None if the pool is empty."""
    if not games:
        return None
    chooser = rng or random
    return chooser.choice(games)
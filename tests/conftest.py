"""Shared pytest fixtures for steam-local-randomizer."""
from __future__ import annotations

from pathlib import Path

import pytest

from steam_randomizer.library_parser import Game


@pytest.fixture
def make_game():
    """Factory for building Game objects in tests."""

    def _make(appid: str = "1", name: str = "Test Game") -> Game:
        return Game(
            appid=appid,
            name=name,
            installdir=name.replace(" ", ""),
            library_path=Path("/tmp/library"),
        )

    return _make
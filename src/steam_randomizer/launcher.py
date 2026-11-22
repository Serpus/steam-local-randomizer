"""Launch games through the Steam protocol."""
from __future__ import annotations

import os
import sys
import webbrowser

from .library_parser import Game


def launch_game(game: Game) -> None:
    """Ask the OS to launch a Steam game by its appid."""
    uri = f"steam://rungameid/{game.appid}"
    if sys.platform == "win32":
        os.startfile(uri)  # type: ignore[attr-defined]
    else:
        webbrowser.open(uri)
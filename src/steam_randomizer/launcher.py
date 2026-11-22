"""Launch games through the Steam protocol (Windows / Linux / Steam Deck)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser

from .library_parser import Game


def launch_game(game: Game) -> None:
    """Ask the OS to launch a Steam game by its appid."""
    uri = f"steam://rungameid/{game.appid}"
    if sys.platform == "win32":
        os.startfile(uri)  # type: ignore[attr-defined]
        return

    # Linux / SteamOS: prefer xdg-open, fall back to the steam binary.
    if shutil.which("xdg-open"):
        try:
            subprocess.Popen(
                ["xdg-open", uri],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except OSError:
            pass

    steam_bin = shutil.which("steam") or shutil.which("flatpak")
    if steam_bin:
        args = [steam_bin, uri]
        if steam_bin.endswith("flatpak"):
            args = ["flatpak", "run", "com.valvesoftware.Steam", uri]
        try:
            subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except OSError:
            pass

    # Last resort: let Python's webbrowser module handle the steam:// URI.
    webbrowser.open(uri)
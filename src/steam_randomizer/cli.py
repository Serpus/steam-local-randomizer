"""Command-line entry point for steam-local-randomizer."""
from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .library_parser import find_installed_games
from .randomizer import filter_games, pick_random_game
from .steam_locator import SteamNotFoundError, find_steam_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="steam-randomizer",
        description="Pick a random game from your locally installed Steam library.",
    )
    parser.add_argument("--list", action="store_true",
                        help="Only list installed games, don't pick.")
    parser.add_argument("--include-tools", action="store_true",
                        help="Include Steam tools (Proton, SteamVR, runtimes) in the pool.")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    return parser


def _pause_if_double_clicked() -> None:
    """Keep the console open when steam-randomizer.exe is double-clicked.

    Triggers only when ALL of the following are true:
      * Windows platform
      * running as a PyInstaller-frozen exe
      * no command-line arguments (double-click passes none)
      * stdin and stdout are both interactive terminals
        (piping or redirecting skips the pause)
      * STEAM_RANDOMIZER_NO_PAUSE env var is not set

    Running from a terminal (`steam-randomizer --list`, piping output, etc.)
    never pauses.
    """
    if sys.platform != "win32":
        return
    if not getattr(sys, "frozen", False):
        return
    if len(sys.argv) > 1:
        return
    if not (sys.stdin and sys.stdin.isatty()):
        return
    if not (sys.stdout and sys.stdout.isatty()):
        return
    if os.environ.get("STEAM_RANDOMIZER_NO_PAUSE"):
        return
    try:
        input("\nНажмите Enter, чтобы закрыть...")
    except (EOFError, KeyboardInterrupt):
        print()


def _main_impl(argv: list[str] | None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        steam_path = find_steam_path()
    except SteamNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Steam found at: {steam_path}", file=sys.stderr)

    games = find_installed_games(steam_path)
    pool = games if args.include_tools else filter_games(games)

    if not pool:
        print("No games found in your Steam library.", file=sys.stderr)
        return 1

    if args.list:
        for game in sorted(pool, key=lambda g: g.name.lower()):
            print(f"{game.appid:>10}  {game.name}")
        print(f"\nTotal: {len(pool)}", file=sys.stderr)
        return 0

    chosen = pick_random_game(pool)
    assert chosen is not None  # pool is not empty
    print(f"Pool size: {len(pool)} games", file=sys.stderr)
    print(f"\n🎲 Your random game: {chosen.name} (appid {chosen.appid})")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _main_impl(argv)
    finally:
        _pause_if_double_clicked()


if __name__ == "__main__":
    raise SystemExit(main())
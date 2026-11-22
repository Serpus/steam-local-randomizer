"""Command-line entry point for steam-local-randomizer."""
from __future__ import annotations

import argparse
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
    parser.add_argument("--list", action="store_true", help="Only list installed games, don't pick.")
    parser.add_argument(
        "--include-tools",
        action="store_true",
        help="Include Steam tools (Proton, SteamVR, runtimes) in the pool.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
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


if __name__ == "__main__":
    raise SystemExit(main())
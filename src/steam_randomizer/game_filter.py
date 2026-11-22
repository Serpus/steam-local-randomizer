"""Filter out unnamed (demo / delisted) games from the full library.

Правило: безымянные записи (`App <id>`) скрываются ТОЛЬКО если интернет
доступен и хотя бы одна другая игра получила настоящее название.
Офлайн — сохраняем всё, чтобы не прятать игры из-за отсутствия сети.
"""
from __future__ import annotations

import re

from .library_parser import Game

_PLACEHOLDER_RE = re.compile(r"^app\s*#?\s*<?(\d+)>?$", re.IGNORECASE)


def is_placeholder_name(appid: str, name: str) -> bool:
    """True, если название — заглушка вида 'App 12345' / 'app #12345' / '12345'."""
    n = (name or "").strip()
    appid = str(appid)
    if n == appid:
        return True
    m = _PLACEHOLDER_RE.match(n)
    return bool(m and m.group(1) == appid)


def hide_unnamed_games(games: list[Game], *, online: bool) -> list[Game]:
    """Убрать безымянные игры, если онлайн и остальные названия получены."""
    if not online:
        return games
    named = [g for g in games if not is_placeholder_name(g.appid, g.name)]
    return named if named else games
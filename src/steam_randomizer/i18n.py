"""Small i18n helpers (currently just Russian pluralization)."""
from __future__ import annotations


def plural_ru(n: int, one: str, few: str, many: str) -> str:
    """Return the correct Russian plural form for a number.

    Args:
        n: the quantity.
        one: form for 1, 21, 31, ... (e.g. "игра").
        few: form for 2-4, 22-24, ... (e.g. "игры").
        many: form for 0, 5-20, 25-30, ... (e.g. "игр").
    """
    n = abs(n) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many
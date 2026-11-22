"""Download and cache Steam game images by appid (no API key).

Sources:
  https://cdn.cloudflare.steamstatic.com/steam/apps/<appid>/header.jpg
  fallback: .../capsule_231x87.jpg

Cache: <config_dir>/icons/<appid>.jpg
Negative cache: <appid>.miss — только после HTTP 404/403 на ВСЕХ источниках
(удалённые из магазина игры), никогда после обычной сетевой ошибки.

Все функции никогда не бросают исключений. fetch_icon() блокирует на сети —
вызывать только из worker-потока, никогда из главного цикла Tk.
"""
from __future__ import annotations

import os
import threading
import urllib.error
import urllib.request
from pathlib import Path

from .settings import config_dir

_CDN = "https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/{name}"
_SOURCES = ("header.jpg", "capsule_231x87.jpg")
_TIMEOUT = 10
_UA = "steam-local-randomizer/1.3"


def _icons_dir() -> Path | None:
    base = config_dir()
    if base is None:
        return None
    return base / "icons"


def _valid_appid(appid: str) -> bool:
    return appid.isdigit() and 0 < len(appid) <= 10


def cached_icon(appid: str) -> Path | None:
    """Путь к закэшированной картинке или None. Без сети, без исключений."""
    appid = str(appid)
    if not _valid_appid(appid):
        return None
    d = _icons_dir()
    if d is None:
        return None
    p = d / f"{appid}.jpg"
    try:
        return p if p.is_file() else None
    except OSError:
        return None


def _download(url: str, dest: Path) -> str:
    """'ok' | 'missing' (HTTP 404/403) | 'error' (сеть/прочее)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = resp.read()
        if not data:
            return "error"
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(f"{dest.stem}.{threading.get_ident()}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, dest)
        return "ok"
    except urllib.error.HTTPError as e:
        return "missing" if e.code in (403, 404) else "error"
    except Exception:
        return "error"


def fetch_icon(appid: str) -> Path | None:
    """Блокирующая: кэш или загрузка. Никогда не бросает. Только worker-потоки."""
    appid = str(appid)
    if not _valid_appid(appid):
        return None
    d = _icons_dir()
    if d is None:
        return None
    p = d / f"{appid}.jpg"
    try:
        if p.is_file():
            return p
        if (d / f"{appid}.miss").is_file():
            return None
    except OSError:
        return None

    statuses: list[str] = []
    for name in _SOURCES:
        st = _download(_CDN.format(appid=appid, name=name), p)
        if st == "ok":
            return p
        statuses.append(st)

    if statuses and all(s == "missing" for s in statuses):
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{appid}.miss").touch()
        except OSError:
            pass
    return None
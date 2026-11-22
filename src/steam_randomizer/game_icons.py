"""Download and cache Steam game images by appid (no API key).

Sources (пробуем по очереди, пока не получим картинку):
  <host>/steam/apps/<appid>/header.jpg
  <host>/steam/apps/<appid>/capsule_231x87.jpg
  host: cdn.cloudflare.steamstatic.com, затем cdn.akamai.steamstatic.com

Cache: <config_dir>/icons/<appid>.jpg
Negative cache: <appid>.miss — ТОЛЬКО после HTTP 404 на всех источниках
(удалённые из магазина / без арта). 403/429/5xx/таймауты — временные,
ретраятся и никогда не пишут .miss.

Все функции никогда не бросают исключений. fetch_icon() блокирует на сети —
вызывать только из worker-потока, никогда из главного цикла Tk.

Debug: STEAM_RANDOMIZER_DEBUG_ICONS=1 — лог причин в stderr.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .settings import config_dir

_HOSTS = (
    "https://cdn.cloudflare.steamstatic.com",
    "https://cdn.akamai.steamstatic.com",
)
_NAMES = ("header.jpg", "capsule_231x87.jpg")
_PATH = "/steam/apps/{appid}/{name}"
_TIMEOUT = 8
_RETRIES = 2
_UA = "steam-local-randomizer/1.3"

_inflight: dict[str, threading.Event] = {}
_inflight_lock = threading.Lock()


def _debug(msg: str) -> None:
    if os.environ.get("STEAM_RANDOMIZER_DEBUG_ICONS"):
        print(f"[game_icons] {msg}", file=sys.stderr)


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
    """'ok' | 'missing' (HTTP 404) | 'error' (сеть/403/429/5xx). С ретраями."""
    for attempt in range(_RETRIES):
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
            if e.code == 404:
                return "missing"
            _debug(f"HTTP {e.code} {url}")
        except Exception as e:  # noqa: BLE001
            _debug(f"{type(e).__name__} {url}: {e}")
        if attempt + 1 < _RETRIES:
            time.sleep(0.5 * (attempt + 1))
    return "error"


def _fetch_locked(appid: str, d: Path, p: Path) -> Path | None:
    """Загрузка лидером (под _inflight_lock)."""
    saw_error = False
    all_missing = True
    for host in _HOSTS:
        for name in _NAMES:
            url = host + _PATH.format(appid=appid, name=name)
            st = _download(url, p)
            if st == "ok":
                _debug(f"ok {appid} <- {url}")
                return p
            if st == "error":
                saw_error = True
                all_missing = False
        if not saw_error:
            # Первый хост дал однозначные 404 — второй хост то же самое.
            break
    if all_missing and not saw_error:
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{appid}.miss").touch()
            _debug(f"missing (404 everywhere) {appid}")
        except OSError:
            pass
    else:
        _debug(f"failed (temporary) {appid}")
    return None


def fetch_icon(appid: str) -> Path | None:
    """Блокирующая: кэш или загрузка. Никогда не бросает. Worker-потоки.

    Одновременные запросы одного appid дедуплицируются: один поток качает,
    остальные ждут и читают кэш.
    """
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

    with _inflight_lock:
        ev = _inflight.get(appid)
        leader = ev is None
        if leader:
            ev = threading.Event()
            _inflight[appid] = ev

    if not leader:
        ev.wait(timeout=_TIMEOUT * _RETRIES * len(_NAMES) * len(_HOSTS) + 5)
        return cached_icon(appid)

    try:
        return _fetch_locked(appid, d, p)
    finally:
        with _inflight_lock:
            _inflight.pop(appid, None)
        ev.set()
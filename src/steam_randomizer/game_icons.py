"""Download and cache Steam game images by appid (no API key).

Cache: <config_dir>/icons/<appid>.jpg
Negative cache: <appid>.miss — только после 404 на всех источниках.
Валидация: принимаем только JPEG/PNG по magic-байтам (HTML-заглушки не кэшируем).
Все функции никогда не бросают. fetch_icon() — только из worker-потоков.
"""
from __future__ import annotations

import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .log import get_logger
from .settings import config_dir

log = get_logger()

_HOSTS = (
    "https://cdn.cloudflare.steamstatic.com",
    "https://cdn.akamai.steamstatic.com",
)
_NAMES = ("header.jpg", "capsule_231x87.jpg")
_PATH = "/steam/apps/{appid}/{name}"
_TIMEOUT = 8
_RETRIES = 2
_UA = "steam-local-randomizer/1.3"

_JPEG = b"\xff\xd8\xff"
_PNG = b"\x89PNG\r\n\x1a\n"

_inflight: dict[str, threading.Event] = {}
_inflight_lock = threading.Lock()


def _icons_dir() -> Path | None:
    base = config_dir()
    return None if base is None else base / "icons"


def _valid_appid(appid: str) -> bool:
    return appid.isdigit() and 0 < len(appid) <= 10


def cached_icon(appid: str) -> Path | None:
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


def _is_image(data: bytes) -> bool:
    return data[:3] == _JPEG or data[:8] == _PNG


def _download(url: str, dest: Path) -> str:
    for attempt in range(_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data = resp.read()
            if not data:
                log.warning("icon %s: empty body from %s", dest.stem, url)
                return "error"
            if not _is_image(data):
                log.warning(
                    "icon %s: NON-IMAGE payload (%d bytes, head=%r) from %s",
                    dest.stem, len(data), data[:16], url,
                )
                return "error"
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(f"{dest.stem}.{threading.get_ident()}.tmp")
            tmp.write_bytes(data)
            os.replace(tmp, dest)
            log.debug("icon %s: downloaded %d bytes <- %s", dest.stem, len(data), url)
            return "ok"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                log.debug("icon %s: 404 %s", dest.stem, url)
                return "missing"
            log.warning("icon %s: HTTP %s %s", dest.stem, e.code, url)
        except Exception as e:  # noqa: BLE001
            log.warning("icon %s: %s %s: %s", dest.stem, type(e).__name__, url, e)
        if attempt + 1 < _RETRIES:
            time.sleep(0.5 * (attempt + 1))
    return "error"


def _fetch_locked(appid: str, d: Path, p: Path) -> Path | None:
    saw_error = False
    all_missing = True
    for host in _HOSTS:
        for name in _NAMES:
            st = _download(host + _PATH.format(appid=appid, name=name), p)
            if st == "ok":
                return p
            if st == "error":
                saw_error = True
                all_missing = False
        if not saw_error:
            break
    if all_missing and not saw_error:
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{appid}.miss").touch()
            log.info("icon %s: marked .miss (404 on all sources)", appid)
        except OSError:
            pass
    else:
        log.warning("icon %s: temporary failure, no cache written", appid)
    return None


def fetch_icon(appid: str) -> Path | None:
    appid = str(appid)
    if not _valid_appid(appid):
        log.warning("icon: invalid appid %r — skipped", appid)
        return None
    d = _icons_dir()
    if d is None:
        log.warning("icon %s: no config dir", appid)
        return None
    p = d / f"{appid}.jpg"
    try:
        if p.is_file():
            log.debug("icon %s: cache hit", appid)
            return p
        if (d / f"{appid}.miss").is_file():
            log.info("icon %s: negative cache (.miss) — skipped, delete file to retry", appid)
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
        log.debug("icon %s: fetching", appid)
        return _fetch_locked(appid, d, p)
    finally:
        with _inflight_lock:
            _inflight.pop(appid, None)
        ev.set()
"""Download and cache Steam game images by appid (no API key).

Cache: <config_dir>/icons/<appid>.jpg
Negative cache: <appid>.miss — с версией схемы. Старые .miss (без версии),
созданные до появления appdetails-фолбэка, автоматически перепроверяются.
Актуальные .miss уважаются до истечения TTL. force=True («⟳») игнорирует .miss.
Валидация: принимаем только JPEG/PNG по magic-байтам.
Все функции никогда не бросают. fetch_icon() — только из worker-потоков.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .log import get_logger
from .settings import config_dir

log = get_logger()

# Источники в порядке приоритета. Угаданные пути — быстрый первый проход.
_SOURCES = (
    ("https://cdn.cloudflare.steamstatic.com", "/steam/apps/{appid}/header.jpg"),
    ("https://cdn.cloudflare.steamstatic.com", "/steam/apps/{appid}/capsule_231x87.jpg"),
    ("https://shared.cloudflare.steamstatic.com", "/store_item_assets/steam/apps/{appid}/header.jpg"),
    ("https://shared.cloudflare.steamstatic.com", "/store_item_assets/steam/apps/{appid}/capsule_231x87.jpg"),
    ("https://cdn.akamai.steamstatic.com", "/steam/apps/{appid}/header.jpg"),
    ("https://shared.akamai.steamstatic.com", "/store_item_assets/steam/apps/{appid}/header.jpg"),
    ("https://cdn.cloudflare.steamstatic.com", "/steam/apps/{appid}/capsule_sm_120.jpg"),
)
_TIMEOUT = 8
_RETRIES = 2
_UA = "steam-local-randomizer/1.3"
_MISS_TTL = 7 * 24 * 3600

# Версия формата .miss. Увеличивать при изменении логики поиска картинок,
# чтобы старые негативные записи автоматически перепроверялись.
# 0 = старые пустые .miss (до версионирования) -> всегда перепроверяются.
_MISS_SCHEMA = 1

_JPEG = b"\xff\xd8\xff"
_PNG = b"\x89PNG\r\n\x1a\n"

_inflight: dict[str, threading.Event] = {}
_inflight_lock = threading.Lock()

# Официальный API для точного URL картинки (фолбэк, когда все CDN-пути 404).
_API_URL = "https://store.steampowered.com/api/appdetails"
_api_lock = threading.Lock()
_api_last = [0.0]
_API_MIN_INTERVAL = 0.4  # щадящий интервал между запросами


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


def _miss_schema(miss: Path) -> int:
    """Версия схемы .miss. Пустой/нечитаемый/старый файл -> 0."""
    try:
        text = miss.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    for line in text.splitlines():
        line = line.strip().lower()
        if line.startswith("schema="):
            try:
                return int(line.split("=", 1)[1].strip())
            except ValueError:
                return 0
    return 0


def _write_miss(d: Path, appid: str, reason: str) -> None:
    try:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{appid}.miss").write_text(
            f"schema={_MISS_SCHEMA}\nts={int(time.time())}\nreason={reason}\n",
            encoding="utf-8",
        )
    except OSError:
        pass


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


def _resolve_via_api(appid: str) -> tuple[str | None, bool]:
    """Точный URL картинки через appdetails.

    Возвращает (url, definitive). definitive=True — API дал окончательный ответ
    (есть картинка или её точно нет). definitive=False — сам запрос не удался,
    надо повторить позже (не помечаем .miss).
    """
    with _api_lock:
        wait = _API_MIN_INTERVAL - (time.monotonic() - _api_last[0])
        if wait > 0:
            time.sleep(wait)
        _api_last[0] = time.monotonic()

    url = f"{_API_URL}?appids={appid}&cc=US&l=en"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        log.warning("icon %s: appdetails request failed: %s %s", appid, type(e).__name__, e)
        return None, False

    entry = data.get(str(appid)) or {}
    if not entry.get("success"):
        log.info("icon %s: appdetails success=false — у приложения нет магазинных данных", appid)
        return None, True
    d = entry.get("data") or {}
    for key in ("capsule_imagev5", "capsule_image", "header_image"):
        u = d.get(key)
        if isinstance(u, str) and u.startswith("http"):
            log.info("icon %s: appdetails resolved %s -> %s", appid, key, u)
            return u, True
    log.info("icon %s: appdetails не вернул ни одного поля с картинкой", appid)
    return None, True


def _fetch_locked(appid: str, d: Path, p: Path) -> Path | None:
    saw_error = False
    all_missing = True
    for host, path_tpl in _SOURCES:
        st = _download(host + path_tpl.format(appid=appid), p)
        if st == "ok":
            return p
        if st == "error":
            saw_error = True
            all_missing = False

    if all_missing and not saw_error:
        # Все угаданные пути 404. Просим у Steam точный URL картинки.
        api_url, definitive = _resolve_via_api(appid)
        if api_url and _download(api_url, p) == "ok":
            return p
        if definitive:
            _write_miss(d, appid, "no_image_cdn_or_api")
            log.info("icon %s: marked .miss schema=%d (нет картинки ни на CDN, ни в API)",
                     appid, _MISS_SCHEMA)
        else:
            log.warning("icon %s: CDN 404 и API недоступен — повторим позже", appid)
    else:
        log.warning("icon %s: temporary failure, no cache written", appid)
    return None


def fetch_icon(appid: str, *, force: bool = False) -> Path | None:
    appid = str(appid)
    if not _valid_appid(appid):
        log.warning("icon: invalid appid %r — skipped", appid)
        return None
    d = _icons_dir()
    if d is None:
        log.warning("icon %s: no config dir", appid)
        return None
    p = d / f"{appid}.jpg"
    miss = d / f"{appid}.miss"
    try:
        if p.is_file():
            log.debug("icon %s: cache hit", appid)
            return p
        if miss.is_file():
            recheck = False
            if force:
                log.info("icon %s: force retry (ignoring .miss)", appid)
                recheck = True
            else:
                schema = _miss_schema(miss)
                if schema < _MISS_SCHEMA:
                    # Старый .miss, созданный до появления новой логики поиска.
                    log.info("icon %s: stale .miss (schema %d < %d) — auto-rechecking",
                             appid, schema, _MISS_SCHEMA)
                    recheck = True
                else:
                    age = time.time() - miss.stat().st_mtime
                    if age > _MISS_TTL:
                        log.info("icon %s: .miss expired (%.1f days) — retrying",
                                 appid, age / 86400)
                        recheck = True
                    else:
                        log.info("icon %s: negative cache (.miss schema %d, %.1f days old) — skipped",
                                 appid, schema, age / 86400)
            if recheck:
                try:
                    miss.unlink()
                except OSError:
                    pass
            else:
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
        ev.wait(timeout=_TIMEOUT * _RETRIES * len(_SOURCES) + 5)
        return cached_icon(appid)

    try:
        log.debug("icon %s: fetching (force=%s)", appid, force)
        return _fetch_locked(appid, d, p)
    finally:
        with _inflight_lock:
            _inflight.pop(appid, None)
        ev.set()
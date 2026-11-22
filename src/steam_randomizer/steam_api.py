"""Fetch game names via Steam's keyless IStoreBrowseService/GetItems.

Endpoint: https://api.steampowered.com/IStoreBrowseService/GetItems/v1/
Up to 100 appids per request. No API key required.
Falls back silently to {} on any network failure.

Cache: per-user config dir (Windows: %APPDATA%, Linux: ~/.config),
       steam-local-randomizer/store_items_cache.json
TTL: 7 days.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .settings import config_dir

_ITEMS_URL = "https://api.steampowered.com/IStoreBrowseService/GetItems/v1/"
_CACHE_FILENAME = "store_items_cache.json"
_CACHE_TTL = timedelta(days=7)
_NETWORK_TIMEOUT = 20
_CHUNK_SIZE = 100          # hard limit for GetItems
_CHUNK_DELAY = 1.0         # seconds between chunks
_COUNTRY_CODE = "US"       # neutral region, avoids RU-specific blocks
_LANGUAGE = "english"

_app_names_memory: dict[str, str] = {}
_fetched_appids: set[str] = set()


def _debug(msg: str) -> None:
    if os.environ.get("STEAM_RANDOMIZER_DEBUG_API"):
        print(f"[steam_api] {msg}", file=sys.stderr)


def _cache_path() -> Path | None:
    base = config_dir()
    if base is None:
        return None
    return base / _CACHE_FILENAME


def _load_cache() -> dict[str, str]:
    path = _cache_path()
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    fetched_at = data.get("fetched_at")
    apps = data.get("apps")
    if not isinstance(fetched_at, str) or not isinstance(apps, dict):
        return {}
    try:
        when = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    except ValueError:
        return {}
    if datetime.now(timezone.utc) - when > _CACHE_TTL:
        return {}
    return {str(k): str(v) for k, v in apps.items() if v}


def _save_cache(apps: dict[str, str]) -> None:
    path = _cache_path()
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "apps": apps,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        _debug(f"saved cache: {path} ({path.stat().st_size} bytes)")
    except OSError as e:
        _debug(f"cache save failed: {e}")


def _fetch_chunk(appids: list[str]) -> dict[str, str]:
    """Request up to 100 appids via GetItems. Returns {appid: name}."""
    input_json = {
        "ids": [{"appid": int(a)} for a in appids],
        "context": {
            "language": _LANGUAGE,
            "country_code": _COUNTRY_CODE,
            "steam_realm": 1,
        },
    }
    params = urllib.parse.urlencode({"input_json": json.dumps(input_json)})
    url = f"{_ITEMS_URL}?{params}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "steam-local-randomizer/1.1"})
        with urllib.request.urlopen(req, timeout=_NETWORK_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        _debug(f"chunk fetch failed: {type(e).__name__}: {e}")
        return {}

    # Response may use snake_case or camelCase depending on Steam's mood.
    response = data.get("response") or data.get("Response") or {}
    items = response.get("store_items") or response.get("storeItems") or []
    if not isinstance(items, list):
        _debug(f"unexpected response keys: {list(response.keys())}")
        return {}

    result: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        appid = item.get("appid")
        name = item.get("name")
        if isinstance(appid, int) and isinstance(name, str) and name:
            result[str(appid)] = name
    return result


def get_app_details(appids: list[str]) -> dict[str, str]:
    """Return {appid: name} for given appids.

    Uses cache → memory → network (in chunks of 100).
    Already-queried appids are never re-queried this session.
    Never raises.
    """
    global _app_names_memory, _fetched_appids

    _app_names_memory.update(_load_cache())

    missing = [
        str(a) for a in appids
        if str(a) not in _app_names_memory and str(a) not in _fetched_appids
    ]
    if not missing:
        return {str(a): _app_names_memory[str(a)] for a in appids if str(a) in _app_names_memory}

    _debug(f"need to fetch {len(missing)} appids")

    fetched: dict[str, str] = {}
    for i in range(0, len(missing), _CHUNK_SIZE):
        chunk = missing[i:i + _CHUNK_SIZE]
        _debug(f"chunk {i // _CHUNK_SIZE + 1}: {len(chunk)} appids")
        fetched.update(_fetch_chunk(chunk))
        _fetched_appids.update(chunk)
        if i + _CHUNK_SIZE < len(missing):
            time.sleep(_CHUNK_DELAY)

    if fetched:
        _app_names_memory.update(fetched)
        _save_cache(_app_names_memory)

    return {str(a): _app_names_memory[str(a)] for a in appids if str(a) in _app_names_memory}


def reset_for_testing() -> None:
    global _app_names_memory, _fetched_appids
    _app_names_memory = {}
    _fetched_appids = set()
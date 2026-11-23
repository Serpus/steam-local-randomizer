"""Offline tests for game_icons: cache, .miss schema versioning, TTL, force, validation, API."""
from __future__ import annotations

import io
import os
import time
import urllib.error

import pytest

from steam_randomizer import game_icons

JPEG = b"\xff\xd8\xff" + b"JPEGDATA"
CAPSULE = b"\xff\xd8\xff" + b"CAPSULE"
AKAMAI = b"\xff\xd8\xff" + b"FROM_AKAMAI"


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(game_icons.time, "sleep", lambda _s: None)
    # Отключаем реальный appdetails-фолбэк в тестах: "картинки точно нет".
    monkeypatch.setattr(game_icons, "_resolve_via_api", lambda a: (None, True))


class _Resp:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_urlopen(monkeypatch, handler):
    calls = []

    def fake(req, timeout=None):
        calls.append(req.full_url)
        return handler(req.full_url)

    monkeypatch.setattr(game_icons.urllib.request, "urlopen", fake)
    return calls


def _404(url):
    raise urllib.error.HTTPError(url, 404, "Not Found", None, io.BytesIO(b""))


def test_invalid_appid_never_touches_network(monkeypatch):
    calls = _patch_urlopen(monkeypatch, lambda url: _Resp(JPEG))
    for bad in ("", "abc", "../evil", "12;rm", "-1"):
        assert game_icons.fetch_icon(bad) is None
        assert game_icons.cached_icon(bad) is None
    assert calls == []


def test_download_and_cache(monkeypatch):
    calls = _patch_urlopen(monkeypatch, lambda url: _Resp(JPEG))
    p = game_icons.fetch_icon("440")
    assert p is not None and p.is_file() and p.read_bytes() == JPEG
    assert len(calls) == 1
    assert game_icons.fetch_icon("440") == p
    assert game_icons.cached_icon("440") == p
    assert len(calls) == 1


def test_fallback_to_capsule(monkeypatch):
    def handler(url):
        if url.endswith("header.jpg") and "store_item_assets" not in url:
            _404(url)
        if url.endswith("capsule_231x87.jpg") and "store_item_assets" not in url:
            return _Resp(CAPSULE)
        _404(url)

    calls = _patch_urlopen(monkeypatch, handler)
    p = game_icons.fetch_icon("1145360")
    assert p is not None and p.read_bytes() == CAPSULE
    assert len(calls) == 2


def test_404_everywhere_writes_versioned_negative_cache(monkeypatch):
    calls = _patch_urlopen(monkeypatch, _404)
    assert game_icons.fetch_icon("999") is None
    assert len(calls) == len(game_icons._SOURCES)
    miss = game_icons._icons_dir() / "999.miss"
    assert miss.is_file()
    assert f"schema={game_icons._MISS_SCHEMA}" in miss.read_text()
    assert game_icons.fetch_icon("999") is None
    assert len(calls) == len(game_icons._SOURCES)


def test_stale_unversioned_miss_is_auto_rechecked(monkeypatch):
    calls = _patch_urlopen(monkeypatch, _404)
    d = game_icons._icons_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "888.miss").touch()  # пустой .miss = старая схема без версии
    assert game_icons.fetch_icon("888") is None
    # сеть дёргалась, потому что старый .miss автоматически перепроверен
    assert len(calls) == len(game_icons._SOURCES)
    # новый .miss уже с актуальной схемой
    assert f"schema={game_icons._MISS_SCHEMA}" in (d / "888.miss").read_text()


def test_current_schema_miss_respected_without_network(monkeypatch):
    calls = _patch_urlopen(monkeypatch, _404)
    d = game_icons._icons_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "888.miss").write_text(
        f"schema={game_icons._MISS_SCHEMA}\nts={int(time.time())}\nreason=x\n"
    )
    assert game_icons.fetch_icon("888") is None
    assert len(calls) == 0  # актуальный .miss уважаем, сеть не трогаем


def test_force_ignores_negative_cache(monkeypatch):
    calls = _patch_urlopen(monkeypatch, _404)
    assert game_icons.fetch_icon("999") is None
    first = len(calls)
    assert game_icons.fetch_icon("999", force=True) is None
    assert len(calls) == first + len(game_icons._SOURCES)


def test_expired_negative_cache_retried(monkeypatch):
    calls = _patch_urlopen(monkeypatch, _404)
    assert game_icons.fetch_icon("999") is None
    miss = game_icons._icons_dir() / "999.miss"
    old = time.time() - game_icons._MISS_TTL - 60
    os.utime(miss, (old, old))
    first = len(calls)
    assert game_icons.fetch_icon("999") is None
    assert len(calls) > first


def test_network_error_retries_and_no_negative_cache(monkeypatch):
    def handler(url):
        raise urllib.error.URLError("offline")

    calls = _patch_urlopen(monkeypatch, handler)
    assert game_icons.fetch_icon("570") is None
    first = len(calls)
    assert first >= 2
    assert game_icons.fetch_icon("570") is None
    assert len(calls) > first


def test_403_is_temporary_not_missing(monkeypatch):
    def handler(url):
        raise urllib.error.HTTPError(url, 403, "Forbidden", None, io.BytesIO(b""))

    calls = _patch_urlopen(monkeypatch, handler)
    assert game_icons.fetch_icon("730") is None
    before = len(calls)
    assert game_icons.fetch_icon("730") is None
    assert len(calls) > before


def test_alternate_host_used_on_error(monkeypatch):
    def handler(url):
        if "cloudflare" in url:
            raise urllib.error.URLError("edge down")
        return _Resp(AKAMAI)

    calls = _patch_urlopen(monkeypatch, handler)
    p = game_icons.fetch_icon("10")
    assert p is not None and p.read_bytes() == AKAMAI
    assert any("akamai" in u for u in calls)


def test_non_image_payload_rejected_and_not_cached(monkeypatch):
    calls = _patch_urlopen(monkeypatch, lambda url: _Resp(b"<html>age gate</html>"))
    assert game_icons.fetch_icon("123") is None
    assert game_icons.cached_icon("123") is None
    assert len(calls) >= 2


def test_api_fallback_when_cdn_404(monkeypatch):
    monkeypatch.setattr(
        game_icons, "_resolve_via_api",
        lambda a: ("https://cdn.example/real.jpg", True),
    )

    def handler(url):
        if url.endswith("real.jpg"):
            return _Resp(JPEG)
        _404(url)

    calls = _patch_urlopen(monkeypatch, handler)
    p = game_icons.fetch_icon("555")
    assert p is not None and p.is_file() and p.read_bytes() == JPEG
    assert any("real.jpg" in c for c in calls)


def test_api_transient_failure_does_not_mark_miss(monkeypatch):
    monkeypatch.setattr(game_icons, "_resolve_via_api", lambda a: (None, False))
    calls = _patch_urlopen(monkeypatch, _404)
    assert game_icons.fetch_icon("777") is None
    assert not (game_icons._icons_dir() / "777.miss").is_file()
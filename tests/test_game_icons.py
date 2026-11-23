"""Offline tests for game_icons: cache, negative cache, retries, validation."""
from __future__ import annotations

import io
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
        if url.endswith("header.jpg"):
            _404(url)
        return _Resp(CAPSULE)

    calls = _patch_urlopen(monkeypatch, handler)
    p = game_icons.fetch_icon("1145360")
    assert p is not None and p.read_bytes() == CAPSULE
    assert len(calls) == 2


def test_404_everywhere_writes_negative_cache(monkeypatch):
    calls = _patch_urlopen(monkeypatch, _404)
    assert game_icons.fetch_icon("999") is None
    assert len(calls) == 2
    assert game_icons.fetch_icon("999") is None
    assert len(calls) == 2


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
"""Tests for steam_api (no real network)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import pytest

from steam_randomizer import steam_api


@pytest.fixture(autouse=True)
def reset(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    steam_api.reset_for_testing()
    yield
    steam_api.reset_for_testing()


def test_empty_list_returns_empty():
    assert steam_api.get_app_details([]) == {}


def test_network_failure_returns_empty(monkeypatch):
    monkeypatch.setattr(steam_api, "_fetch_chunk", lambda ids: {})
    assert steam_api.get_app_details(["10", "20"]) == {}


def test_uses_cache(tmp_path, monkeypatch):
    cache_dir = tmp_path / "steam-local-randomizer"
    cache_dir.mkdir(parents=True)
    (cache_dir / "store_items_cache.json").write_text(
        '{"fetched_at": "2099-01-01T00:00:00+00:00", "apps": {"10": "Counter-Strike"}}',
        encoding="utf-8",
    )
    assert steam_api.get_app_details(["10"]) == {"10": "Counter-Strike"}


def test_fetches_and_caches(tmp_path, monkeypatch):
    fake = {"1145360": "Hades"}
    monkeypatch.setattr(steam_api, "_fetch_chunk", lambda ids: fake)
    assert steam_api.get_app_details(["1145360"]) == fake
    assert (tmp_path / "steam-local-randomizer" / "store_items_cache.json").is_file()


def test_progress_callback_reports_chunks(monkeypatch):
    monkeypatch.setattr(
        steam_api, "_fetch_chunk", lambda ids: {i: f"Game {i}" for i in ids}
    )
    seen = []
    steam_api.get_app_details(
        ["1", "2"], on_progress=lambda done, total: seen.append((done, total))
    )
    assert seen == [(2, 2)]


def test_stale_entry_expires_even_if_file_is_fresh(tmp_path, monkeypatch):
    cache_dir = tmp_path / "steam-local-randomizer"
    cache_dir.mkdir(parents=True)
    old = time.time() - 8 * 24 * 3600
    (cache_dir / "store_items_cache.json").write_text(
        json.dumps({
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "apps": {"10": "Old Name", "20": "Fresh Name"},
            "apps_fetched_at": {"10": old, "20": time.time()},
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(steam_api, "_fetch_chunk", lambda ids: {i: "New Name" for i in ids})
    assert steam_api.get_app_details(["10", "20"]) == {
        "10": "New Name",
        "20": "Fresh Name",
    }
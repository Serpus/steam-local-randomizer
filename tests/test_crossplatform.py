"""Tests for cross-platform steam_locator and launcher (Linux / Steam Deck)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from steam_randomizer import launcher, settings as settings_mod
from steam_randomizer.steam_locator import (
    SteamNotFoundError,
    _looks_like_steam,
    find_steam_path,
)


def test_find_steam_path_env_override(tmp_path, monkeypatch):
    """STEAM_PATH env var wins on Linux."""
    monkeypatch.setenv("STEAM_PATH", str(tmp_path))
    if sys.platform == "win32":
        pytest.skip("Linux-only behaviour")
    assert find_steam_path() == tmp_path


def test_find_steam_path_dot_steam_root(tmp_path, monkeypatch):
    """~/.steam/root with steamapps is detected."""
    if sys.platform == "win32":
        pytest.skip("Linux-only behaviour")
    monkeypatch.delenv("STEAM_PATH", raising=False)
    fake_home = tmp_path / "home"
    steam_root = fake_home / ".steam" / "root"
    (steam_root / "steamapps").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    import steam_randomizer.steam_locator as loc

    # Also patch the module-level tuple built at import time with the real home.
    old = loc._LINUX_FALLBACK_PATHS
    monkeypatch.setattr(loc, "_LINUX_FALLBACK_PATHS", (steam_root,))
    try:
        assert find_steam_path() == steam_root
    finally:
        loc._LINUX_FALLBACK_PATHS = old


def test_find_steam_path_raises_when_nothing_found(tmp_path, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("Linux-only behaviour")
    monkeypatch.delenv("STEAM_PATH", raising=False)
    fake_home = tmp_path / "empty-home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    import steam_randomizer.steam_locator as loc

    monkeypatch.setattr(loc, "_LINUX_FALLBACK_PATHS", ())
    with pytest.raises(SteamNotFoundError):
        find_steam_path()


def test_looks_like_steam(tmp_path):
    assert not _looks_like_steam(tmp_path)
    (tmp_path / "steamapps").mkdir()
    assert _looks_like_steam(tmp_path)


def test_launch_game_linux_xdg_open(monkeypatch, tmp_path):
    """On non-Windows, launch_game uses xdg-open when available."""
    if sys.platform == "win32":
        pytest.skip("Linux-only behaviour")

    calls: list[list[str]] = []

    class FakeProc:
        pass

    def fake_which(name):
        return "/usr/bin/xdg-open" if name == "xdg-open" else None

    def fake_popen(args, **kwargs):
        calls.append(list(args))
        return FakeProc()

    from steam_randomizer.library_parser import Game

    monkeypatch.setattr(launcher.shutil, "which", fake_which)
    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)

    launcher.launch_game(Game("440", "TF2", "tf", Path("/x")))
    assert calls == [["xdg-open", "steam://rungameid/440"]]


def test_launch_game_linux_flatpak_fallback(monkeypatch):
    """Without xdg-open but with flatpak, use flatpak run com.valvesoftware.Steam."""
    if sys.platform == "win32":
        pytest.skip("Linux-only behaviour")

    calls: list[list[str]] = []

    def fake_which(name):
        return "/usr/bin/flatpak" if name == "flatpak" else None

    def fake_popen(args, **kwargs):
        calls.append(list(args))

    from steam_randomizer.library_parser import Game

    monkeypatch.setattr(launcher.shutil, "which", fake_which)
    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)

    launcher.launch_game(Game("440", "TF2", "tf", Path("/x")))
    assert calls == [["flatpak", "run", "com.valvesoftware.Steam", "steam://rungameid/440"]]


def test_config_dir_linux_xdg(tmp_path, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("Linux-only behaviour")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert settings_mod.config_dir() == tmp_path / "steam-local-randomizer"


def test_config_dir_linux_default_home(tmp_path, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("Linux-only behaviour")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert settings_mod.config_dir() == tmp_path / ".config" / "steam-local-randomizer"

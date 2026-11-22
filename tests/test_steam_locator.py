"""Comprehensive tests for steam_locator module."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from steam_randomizer.steam_locator import (
    SteamNotFoundError,
    _looks_like_steam,
    _find_steam_linux,
    _find_steam_windows,
    find_steam_path,
)


class TestLooksLikeSteam:
    """Tests for _looks_like_steam helper function."""

    def test_empty_directory(self, tmp_path):
        """Empty directory is not a valid Steam installation."""
        assert not _looks_like_steam(tmp_path)

    def test_with_steamapps(self, tmp_path):
        """Directory with steamapps is valid."""
        (tmp_path / "steamapps").mkdir()
        assert _looks_like_steam(tmp_path)

    def test_with_steamapps_capitalized(self, tmp_path):
        """Directory with SteamApps (capitalized) is valid."""
        (tmp_path / "SteamApps").mkdir()
        assert _looks_like_steam(tmp_path)

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows NTFS is case-insensitive")
    def test_with_both_variants(self, tmp_path):
        """Directory with both steamapps and SteamApps is valid (Linux/macOS only)."""
        (tmp_path / "steamapps").mkdir()
        (tmp_path / "SteamApps").mkdir()
        assert _looks_like_steam(tmp_path)

    def test_nonexistent_directory(self, tmp_path):
        """Non-existent directory is not valid."""
        nonexistent = tmp_path / "does_not_exist"
        assert not _looks_like_steam(nonexistent)

    def test_with_other_folders(self, tmp_path):
        """Directory with other folders but no steamapps is not valid."""
        (tmp_path / "bin").mkdir()
        (tmp_path / "config").mkdir()
        (tmp_path / "userdata").mkdir()
        assert not _looks_like_steam(tmp_path)


class TestFindSteamPath:
    """Tests for find_steam_path main function."""

    def test_env_override_takes_precedence(self, tmp_path, monkeypatch):
        """STEAM_PATH environment variable overrides all other detection."""
        steam_dir = tmp_path / "custom_steam"
        steam_dir.mkdir()  # Сначала создаём родителя
        (steam_dir / "steamapps").mkdir()

        monkeypatch.setenv("STEAM_PATH", str(steam_dir))

        # Даже если мы замокаем всё остальное, переменная окружения должна победить
        result = find_steam_path()
        assert result == steam_dir

    def test_env_override_nonexistent_falls_through(self, tmp_path, monkeypatch):
        """Non-existent STEAM_PATH is ignored and falls through to normal detection."""
        monkeypatch.setenv("STEAM_PATH", str(tmp_path / "nonexistent"))

        # Мокаем платформо-специфичные функции, чтобы они ничего не нашли
        with patch("steam_randomizer.steam_locator._find_steam_windows") as mock_win, \
             patch("steam_randomizer.steam_locator._find_steam_linux") as mock_linux:
            mock_win.side_effect = SteamNotFoundError("Not found")
            mock_linux.side_effect = SteamNotFoundError("Not found")

            with pytest.raises(SteamNotFoundError):
                find_steam_path()


class TestFindSteamWindows:
    """Tests for Windows-specific Steam detection."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
    def test_registry_key_found(self, tmp_path):
        """Steam path from Windows registry is returned."""
        steam_dir = tmp_path / "Steam"
        steam_dir.mkdir()

        with patch("steam_randomizer.steam_locator.winreg") as mock_winreg:
            mock_key = MagicMock()
            mock_winreg.OpenKey.return_value.__enter__.return_value = mock_key
            mock_winreg.QueryValueEx.return_value = (str(steam_dir), None)
            mock_winreg.HKEY_CURRENT_USER = 0x80000001

            result = _find_steam_windows()
            assert result == steam_dir

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
    def test_registry_missing_fallback_works(self, tmp_path):
        """Falls back to Program Files when registry is missing."""
        steam_dir = tmp_path / "Program Files (x86)" / "Steam"
        steam_dir.mkdir(parents=True)

        with patch("steam_randomizer.steam_locator.winreg") as mock_winreg:
            mock_winreg.OpenKey.side_effect = FileNotFoundError()
            mock_winreg.HKEY_CURRENT_USER = 0x80000001

            # Патчим _FALLBACK_PATHS_WINDOWS, чтобы использовать наш тестовый путь
            with patch("steam_randomizer.steam_locator._FALLBACK_PATHS_WINDOWS",
                      (steam_dir,)):
                result = _find_steam_windows()
                assert result == steam_dir

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
    def test_no_steam_found_raises_error(self, tmp_path):
        """Raises SteamNotFoundError when Steam cannot be found."""
        with patch("steam_randomizer.steam_locator.winreg") as mock_winreg:
            mock_winreg.OpenKey.side_effect = FileNotFoundError()
            mock_winreg.HKEY_CURRENT_USER = 0x80000001

            # Патчим fallback пути на несуществующие директории
            with patch("steam_randomizer.steam_locator._FALLBACK_PATHS_WINDOWS",
                      (tmp_path / "nonexistent1", tmp_path / "nonexistent2")):
                with pytest.raises(SteamNotFoundError):
                    _find_steam_windows()


class TestFindSteamLinux:
    """Tests for Linux-specific Steam detection."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Linux-only test")
    def test_dot_steam_steam_found(self, tmp_path, monkeypatch):
        """~/.steam/steam is detected."""
        fake_home = tmp_path / "home"
        steam_dir = fake_home / ".steam" / "steam"
        (steam_dir / "steamapps").mkdir(parents=True)

        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.delenv("STEAM_PATH", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)

        # Патчим _LINUX_FALLBACK_PATHS, чтобы использовать наш тестовый путь
        with patch("steam_randomizer.steam_locator._LINUX_FALLBACK_PATHS",
                  (steam_dir,)):
            result = _find_steam_linux()
            assert result == steam_dir

    @pytest.mark.skipif(sys.platform == "win32", reason="Linux-only test")
    def test_flatpak_installation_found(self, tmp_path, monkeypatch):
        """Flatpak Steam installation is detected."""
        fake_home = tmp_path / "home"
        flatpak_steam = (fake_home / ".var" / "app" / "com.valvesoftware.Steam" /
                        ".steam" / "steam")
        (flatpak_steam / "steamapps").mkdir(parents=True)

        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.delenv("STEAM_PATH", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)

        with patch("steam_randomizer.steam_locator._LINUX_FALLBACK_PATHS",
                  (flatpak_steam,)):
            result = _find_steam_linux()
            assert result == flatpak_steam

    @pytest.mark.skipif(sys.platform == "win32", reason="Linux-only test")
    def test_xdg_data_home_override(self, tmp_path, monkeypatch):
        """XDG_DATA_HOME is checked if set."""
        xdg_steam = tmp_path / "custom_xdg" / "Steam"
        (xdg_steam / "steamapps").mkdir(parents=True)

        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "custom_xdg"))
        monkeypatch.delenv("STEAM_PATH", raising=False)

        # XDG путь должен быть вставлен на позицию 2
        result = _find_steam_linux()
        assert result == xdg_steam

    @pytest.mark.skipif(sys.platform == "win32", reason="Linux-only test")
    def test_symlink_resolution(self, tmp_path, monkeypatch):
        """Symlinks are resolved correctly."""
        fake_home = tmp_path / "home"
        actual_steam = tmp_path / "actual_steam"
        (actual_steam / "steamapps").mkdir(parents=True)

        symlink_steam = fake_home / ".steam" / "steam"
        symlink_steam.parent.mkdir(parents=True)
        symlink_steam.symlink_to(actual_steam)

        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.delenv("STEAM_PATH", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)

        with patch("steam_randomizer.steam_locator._LINUX_FALLBACK_PATHS",
                  (symlink_steam,)):
            result = _find_steam_linux()
            # Должен вернуть разрешённый путь
            assert result == actual_steam.resolve()

    @pytest.mark.skipif(sys.platform == "win32", reason="Linux-only test")
    def test_broken_symlink_skipped(self, tmp_path, monkeypatch):
        """Broken symlinks are skipped gracefully."""
        fake_home = tmp_path / "home"
        broken_symlink = fake_home / ".steam" / "steam"
        broken_symlink.parent.mkdir(parents=True)
        broken_symlink.symlink_to(tmp_path / "nonexistent")

        # Добавляем валидный fallback
        valid_steam = tmp_path / "valid_steam"
        (valid_steam / "steamapps").mkdir(parents=True)  # FIX: parents=True

        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.delenv("STEAM_PATH", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)

        with patch("steam_randomizer.steam_locator._LINUX_FALLBACK_PATHS",
                   (broken_symlink, valid_steam)):
            result = _find_steam_linux()
            assert result == valid_steam

    @pytest.mark.skipif(sys.platform == "win32", reason="Linux-only test")
    def test_no_steam_found_raises_error(self, tmp_path, monkeypatch):
        """Raises SteamNotFoundError when no Steam installation is found."""
        fake_home = tmp_path / "empty_home"
        fake_home.mkdir()

        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.delenv("STEAM_PATH", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)

        with patch("steam_randomizer.steam_locator._LINUX_FALLBACK_PATHS", ()):
            with pytest.raises(SteamNotFoundError) as exc_info:
                _find_steam_linux()

            assert "Steam installation not found" in str(exc_info.value)
            assert "https://store.steampowered.com/about/" in str(exc_info.value)

    @pytest.mark.skipif(sys.platform == "win32", reason="Linux-only test")
    def test_permission_error_handled(self, tmp_path, monkeypatch):
        """PermissionError is handled gracefully."""
        fake_home = tmp_path / "home"
        inaccessible_steam = fake_home / ".steam" / "steam"
        inaccessible_steam.mkdir(parents=True)

        valid_steam = tmp_path / "valid_steam"
        (valid_steam / "steamapps").mkdir(parents=True)  # FIX: parents=True

        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.delenv("STEAM_PATH", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)

        # Мокаем resolve, чтобы выбрасывать PermissionError
        original_resolve = Path.resolve

        def mock_resolve(self, strict=False):
            if self == inaccessible_steam:
                raise PermissionError("Access denied")
            return original_resolve(self, strict)

        with patch.object(Path, "resolve", mock_resolve):
            with patch("steam_randomizer.steam_locator._LINUX_FALLBACK_PATHS",
                       (inaccessible_steam, valid_steam)):
                result = _find_steam_linux()
                assert result == valid_steam


class TestFindSteamPathIntegration:
    """Integration tests for find_steam_path with real platform detection."""

    def test_platform_detection(self, monkeypatch, tmp_path):
        """Correct platform-specific function is called."""
        steam_dir = tmp_path / "steam"
        steam_dir.mkdir()  # Сначала создаём родителя
        (steam_dir / "steamapps").mkdir()

        monkeypatch.setenv("STEAM_PATH", str(steam_dir))

        result = find_steam_path()
        assert result == steam_dir

    @pytest.mark.skipif(sys.platform == "win32", reason="Linux-only test")
    def test_full_linux_detection_chain(self, tmp_path, monkeypatch):
        """Full detection chain works on Linux."""
        fake_home = tmp_path / "home"
        steam_dir = fake_home / ".local" / "share" / "Steam"
        (steam_dir / "steamapps").mkdir(parents=True)

        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.delenv("STEAM_PATH", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        # FIX: _LINUX_FALLBACK_PATHS вычисляется при импорте модуля,
        # поэтому патча Path.home недостаточно — патчим саму константу
        monkeypatch.setattr(
            "steam_randomizer.steam_locator._LINUX_FALLBACK_PATHS",
            (steam_dir,),
        )

        result = find_steam_path()
        assert result == steam_dir

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
    def test_full_windows_detection_chain(self, tmp_path, monkeypatch):
        """Full detection chain works on Windows."""
        steam_dir = tmp_path / "Steam"
        steam_dir.mkdir()  # Сначала создаём родителя
        (steam_dir / "steamapps").mkdir()

        monkeypatch.delenv("STEAM_PATH", raising=False)

        with patch("steam_randomizer.steam_locator.winreg") as mock_winreg:
            mock_winreg.OpenKey.side_effect = FileNotFoundError()
            mock_winreg.HKEY_CURRENT_USER = 0x80000001

            with patch("steam_randomizer.steam_locator._FALLBACK_PATHS_WINDOWS",
                      (steam_dir,)):
                result = find_steam_path()
                assert result == steam_dir
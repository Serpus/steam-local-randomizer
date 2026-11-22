"""Загрузка и кэш иконок игр. Не знает о виджетах — только о callback'ах.

IconService получает schedule (вызов в главном потоке Tk) и отдаёт готовые
CTkImage через on_ready. Вся работа с сетью — в worker-потоках, создание
CTkImage — только в главном потоке.
"""
from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from pathlib import Path

import customtkinter as ctk

try:
    from PIL import Image, ImageDraw
    PIL_OK = True
except ImportError:  # Pillow не установлен — иконки отключены, приложение работает
    PIL_OK = False

from ..game_icons import cached_icon, fetch_icon

RESULT_SIZE = (320, 150)
LIST_SIZE = (112, 52)
RESULT_RADIUS = 10
LIST_RADIUS = 6


def make_icon_image(path: Path, size: tuple[int, int], radius: int) -> ctk.CTkImage | None:
    """jpg -> скруглённый CTkImage (2x для HiDPI). Только главный поток Tk."""
    if not PIL_OK:
        return None
    try:
        with Image.open(path) as im:
            img = im.convert("RGB")
        img = img.resize((size[0] * 2, size[1] * 2), Image.Resampling.LANCZOS)
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, img.size[0] - 1, img.size[1] - 1), radius=radius * 2, fill=255
        )
        img.putalpha(mask)
        return ctk.CTkImage(light_image=img, dark_image=img, size=size)
    except Exception:
        return None


class IconService:
    """Кэш иконок в памяти + фоновая загрузка. Потокобезопасен по выдаче."""

    def __init__(self, schedule: Callable[..., None]) -> None:
        self._schedule = schedule
        self._mem: dict[tuple[str, tuple[int, int]], ctk.CTkImage] = {}

    def cached(self, appid: str, size: tuple[int, int], radius: int) -> ctk.CTkImage | None:
        """Главный поток: из памяти или с диска, без сети."""
        if not PIL_OK:
            return None
        key = (appid, size)
        img = self._mem.get(key)
        if img is not None:
            return img
        path = cached_icon(appid)
        if path is None:
            return None
        img = make_icon_image(path, size, radius)
        if img is not None:
            self._mem[key] = img
        return img

    def _deliver(self, appid, size, radius, path, on_ready) -> None:
        key = (appid, size)
        img = self._mem.get(key) or make_icon_image(path, size, radius)
        if img is None:
            return
        self._mem[key] = img
        try:
            on_ready(img)
        except Exception:
            pass

    def request(self, appid: str, size, radius, on_ready: Callable) -> None:
        """Одна иконка: мгновенно из кэша или в фоне."""
        if not PIL_OK:
            return
        img = self.cached(appid, size, radius)
        if img is not None:
            on_ready(img)
            return

        def work() -> None:
            path = fetch_icon(appid)
            if path is not None:
                self._schedule(self._deliver, appid, size, radius, path, on_ready)

        threading.Thread(target=work, daemon=True).start()

    def request_many(self, tasks: list[tuple[str, Callable]], size, radius, workers: int = 3) -> None:
        """Список (appid, on_ready). Кэшированные — сразу, остальные — пул потоков."""
        if not PIL_OK or not tasks:
            return
        q: queue.Queue = queue.Queue()
        for appid, on_ready in tasks:
            img = self.cached(appid, size, radius)
            if img is not None:
                on_ready(img)
            else:
                q.put((appid, on_ready))
        if q.empty():
            return

        def work() -> None:
            while True:
                try:
                    appid, on_ready = q.get_nowait()
                except queue.Empty:
                    return
                path = fetch_icon(appid)
                if path is not None:
                    self._schedule(self._deliver, appid, size, radius, path, on_ready)

        for _ in range(workers):
            threading.Thread(target=work, daemon=True).start()
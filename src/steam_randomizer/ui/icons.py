"""Загрузка и кэш иконок. Не знает о виджетах — только о callback'ах."""
from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from pathlib import Path

import customtkinter as ctk

try:
    from PIL import Image, ImageDraw
    PIL_OK = True
except ImportError:
    PIL_OK = False

from ..game_icons import cached_icon, fetch_icon
from ..log import get_logger

log = get_logger()

RESULT_SIZE = (320, 150)
LIST_SIZE = (112, 52)
RESULT_RADIUS = 10
LIST_RADIUS = 6


def make_icon_image(path: Path, size: tuple[int, int], radius: int) -> ctk.CTkImage | None:
    """jpg -> скруглённый CTkImage. Битый кэш логируем и удаляем (само-лечение)."""
    if not PIL_OK:
        log.warning("icon %s: Pillow not installed — icons disabled", path.stem)
        return None
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            img = im.convert("RGB")
        img = img.resize((size[0] * 2, size[1] * 2), Image.Resampling.LANCZOS)
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, img.size[0] - 1, img.size[1] - 1), radius=radius * 2, fill=255
        )
        img.putalpha(mask)
        return ctk.CTkImage(light_image=img, dark_image=img, size=size)
    except Exception as e:  # noqa: BLE001
        log.warning("icon %s: CORRUPT cached image (%s) — removing bad cache", path.stem, e)
        try:
            path.unlink()
        except OSError:
            pass
        return None


class IconService:
    def __init__(self, schedule: Callable[..., None]) -> None:
        self._schedule = schedule
        self._mem: dict[tuple[str, tuple[int, int]], ctk.CTkImage] = {}

    def cached(self, appid: str, size, radius) -> ctk.CTkImage | None:
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
            log.warning("icon %s: deliver failed (image build)", appid)
            return
        self._mem[key] = img
        try:
            on_ready(img)
            log.debug("icon %s: delivered to widget", appid)
        except Exception:
            log.exception("icon %s: on_ready raised", appid)

    def request(self, appid: str, size, radius, on_ready: Callable, *, force: bool = False) -> None:
        if not PIL_OK:
            return
        img = self.cached(appid, size, radius)
        if img is not None:
            on_ready(img)
            return

        def work() -> None:
            path = fetch_icon(appid, force=force)
            if path is None:
                log.debug("icon %s: fetch returned None", appid)
                return
            self._schedule(self._deliver, appid, size, radius, path, on_ready)

        threading.Thread(target=work, daemon=True).start()

    def request_many(
        self,
        tasks: list[tuple[str, Callable]],
        size,
        radius,
        workers: int = 3,
        *,
        force: bool = False,
    ) -> None:
        if not PIL_OK or not tasks:
            return
        q: queue.Queue = queue.Queue()
        immediate = 0
        for appid, on_ready in tasks:
            img = self.cached(appid, size, radius)
            if img is not None:
                immediate += 1
                try:
                    on_ready(img)
                except Exception:
                    log.exception("icon %s: on_ready (cached) raised", appid)
            else:
                q.put((appid, on_ready))
        log.debug(
            "icons: %d tasks (%d cached, %d to fetch, force=%s)",
            len(tasks), immediate, q.qsize(), force,
        )
        if q.empty():
            return

        def work() -> None:
            while True:
                try:
                    appid, on_ready = q.get_nowait()
                except queue.Empty:
                    return
                path = fetch_icon(appid, force=force)
                if path is None:
                    log.debug("icon %s: fetch returned None", appid)
                    continue
                self._schedule(self._deliver, appid, size, radius, path, on_ready)

        for _ in range(workers):
            threading.Thread(target=work, daemon=True).start()
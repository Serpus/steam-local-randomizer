"""Окно настроек: управление чёрным списком и другими параметрами.

Сейчас содержит раздел «Чёрный список»:
  - галочка «Не учитывать игры из чёрного списка»,
  - список игр в чёрном списке с кнопками удаления,
  - кнопка «Очистить весь чёрный список».

При изменении списка через колбэк `on_blacklist_changed` уведомляется
главное окно, чтобы синхронизировать окно «Все игры».
"""
from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from .. import settings as app_settings
from ..i18n import plural_ru
from ..library_parser import Game
from ..log import get_logger

log = get_logger()

_ROW_BG = "#313131"
_ROW_HOVER = "#3d3d3d"


class SettingsWindow(ctk.CTkToplevel):
    def __init__(
        self,
        master,
        *,
        games: list[Game],
        on_blacklist_changed: Callable[[set[str]], None],
    ) -> None:
        super().__init__(master)
        self._games_by_id = {g.appid: g for g in games}
        self._on_blacklist_changed_cb = on_blacklist_changed

        self.title("Настройки")
        self.geometry("500x560")
        self.minsize(420, 400)
        self.transient(master)
        self.after(10, self.grab_set)

        self._build_ui()

    def _build_ui(self) -> None:
        # Заголовок раздела
        ctk.CTkLabel(
            self, text="⛔ Чёрный список", font=("", 16, "bold")
        ).pack(pady=(18, 4))

        # Описание
        ctk.CTkLabel(
            self,
            text="Игры из чёрного списка никогда не выпадают в рулетке.",
            font=("", 12), text_color=("gray50", "gray60"),
        ).pack(pady=(0, 10))

        # Галочка
        self._use_var = ctk.BooleanVar(value=app_settings.is_use_blacklist())
        self._use_check = ctk.CTkCheckBox(
            self,
            text="Не учитывать игры из чёрного списка",
            variable=self._use_var,
            command=self._on_use_toggle,
            height=30,
            font=("", 13),
        )
        self._use_check.pack(fill="x", padx=22, pady=(0, 12))

        # Количество игр в чёрном списке
        self._count_label = ctk.CTkLabel(
            self, text="", font=("", 12), anchor="w",
        )
        self._count_label.pack(fill="x", padx=22)

        # Скроллируемый список игр
        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True, padx=22, pady=(10, 10))

        # Кнопка очистки внизу
        self._clear_btn = ctk.CTkButton(
            self,
            text="Очистить весь чёрный список",
            height=36,
            fg_color="#7a2e2e",
            hover_color="#964040",
            command=self._on_clear,
        )
        self._clear_btn.pack(fill="x", padx=22, pady=(0, 16))

        self._render_list()

    def _render_list(self) -> None:
        for w in self._scroll.winfo_children():
            w.destroy()

        bl = app_settings.get_blacklist()
        count = len(bl)
        word = plural_ru(count, "игра", "игры", "игр")
        self._count_label.configure(text=f"В чёрном списке: {count} {word}")

        if count == 0:
            ctk.CTkLabel(
                self._scroll,
                text="Чёрный список пуст",
                text_color=("gray50", "gray55"),
            ).pack(pady=24)
            self._clear_btn.configure(state="disabled")
            return

        self._clear_btn.configure(state="normal")

        # Сортируем игры в чёрном списке по имени
        blacklisted_games = []
        for appid in bl:
            game = self._games_by_id.get(appid)
            if game is not None:
                blacklisted_games.append(game)
        blacklisted_games.sort(key=lambda g: g.name.lower())

        for game in blacklisted_games:
            row = ctk.CTkFrame(self._scroll, fg_color=_ROW_BG, corner_radius=6)
            row.pack(fill="x", pady=2)

            # Кнопка удаления
            remove_btn = ctk.CTkButton(
                row,
                text="✕",
                width=32,
                height=28,
                fg_color="#7a2e2e",
                hover_color="#964040",
                command=lambda g=game: self._on_remove(g),
            )
            remove_btn.pack(side="right", padx=(4, 8), pady=6)

            # Иконка (эмодзи)
            icon = ctk.CTkLabel(
                row, text="🎮", font=("", 14),
                text_color=("gray60", "gray35"), anchor="w",
            )
            icon.pack(side="left", padx=(8, 4), pady=6)

            # Название
            name = ctk.CTkLabel(
                row, text=game.name, anchor="w", justify="left",
                font=("", 13), wraplength=340,
            )
            name.pack(side="left", fill="x", expand=True, padx=(4, 0), pady=6)

    def _on_use_toggle(self) -> None:
        app_settings.set_use_blacklist(self._use_var.get())
        log.info("settings: use_blacklist = %s", self._use_var.get())
        self._on_blacklist_changed_cb(app_settings.get_blacklist())

    def _on_remove(self, game: Game) -> None:
        log.info("settings: removing %s (appid %s) from blacklist", game.name, game.appid)
        app_settings.toggle_blacklist(game.appid)
        self._render_list()
        self._on_blacklist_changed_cb(app_settings.get_blacklist())

    def _on_clear(self) -> None:
        log.info("settings: clearing entire blacklist")
        app_settings.clear_blacklist()
        self._render_list()
        self._on_blacklist_changed_cb(app_settings.get_blacklist())
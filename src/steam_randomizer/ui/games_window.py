"""Окно «Все игры»: виртуализированный список (только видимые строки).

400+ игр не фризит: в памяти лишь видимые строки (+буфер), поиск не
пересоздаёт тысячи виджетов, иконки грузятся только для видимых строк.
«⟳» принудительно перепроверяет видимые иконки, игнорируя .miss.
"""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk

from ..i18n import plural_ru
from ..library_parser import Game
from ..launcher import launch_game
from ..log import get_logger
from . import icons

log = get_logger()

ROW_H = 88
BUFFER = 4
_CANVAS_BG = "#242424"
_ROW_BG = "#313131"
_ROW_HOVER = "#3d3d3d"


def _matches(game: Game, query: str) -> bool:
    q = query.strip().lower()
    if not q:
        return True
    return q in game.name.lower() or q in game.appid


class AllGamesWindow(ctk.CTkToplevel):
    def __init__(
        self,
        master,
        *,
        games: list[Game],
        installed_ids: set[str],
        use_full_library: bool,
        icon_service,
        on_open_store: Callable[[Game], None],
    ) -> None:
        super().__init__(master)
        self._games = games
        self._installed_ids = installed_ids
        self._full = use_full_library
        self._icons = icon_service
        self._open_store = on_open_store

        self._filtered: list[Game] = []
        self._rows: dict[int, tuple] = {}
        self._content_w = 460
        self._render_pending: str | None = None
        self._search_after: str | None = None
        self._empty_item = None
        self._force_icons = False

        self.title("Вся библиотека" if self._full else "Все установленные игры")
        self.geometry("520x660")
        self.minsize(420, 480)
        self.transient(master)
        self.after(10, self.grab_set)

        count = len(games)
        word = plural_ru(count, "игра", "игры", "игр")
        self._base_title = (
            f"Вся библиотека: {count} {word}" if self._full
            else f"Установлено {count} {word}"
        )
        self._title = ctk.CTkLabel(self, text=self._base_title, font=("", 14, "bold"))
        self._title.pack(pady=(14, 6))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=(0, 8))
        self._search_var = ctk.StringVar(value="")
        self._search = ctk.CTkEntry(
            bar, textvariable=self._search_var,
            placeholder_text="🔍  Поиск по названию или appid…", height=34,
        )
        self._search.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(bar, text="⟳", width=34, height=34, command=self._refresh).pack(
            side="right", padx=(6, 0)
        )

        self._footer = ctk.CTkLabel(
            self, text="Наведите на игру, чтобы увидеть полное название",
            font=("", 11), text_color=("gray45", "gray55"), anchor="w",
        )
        self._footer.pack(side="bottom", fill="x", padx=14, pady=(0, 8))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        self._canvas = tk.Canvas(
            body, bg=_CANVAS_BG, highlightthickness=0, bd=0, yscrollincrement=ROW_H
        )
        self._scroll = ctk.CTkScrollbar(body, command=self._yview)
        self._scroll.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._canvas.configure(yscrollcommand=self._scroll_set)

        self._empty = ctk.CTkLabel(
            self._canvas, text="Ничего не найдено", text_color=("gray50", "gray55")
        )

        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self._canvas.bind(seq, self._wheel)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        self._search.bind("<KeyRelease>", self._on_key)
        self._search.bind("<Escape>", lambda _e: (self._search_var.set(""), self._apply_filter("")))
        self.after(60, self._search.focus_set)

        self._apply_filter("")

    # ---- фильтр / поиск ----------------------------------------------

    def _on_key(self, _event=None) -> None:
        if self._search_after is not None:
            try:
                self.after_cancel(self._search_after)
            except Exception:
                pass
        self._search_after = self.after(150, lambda: self._apply_filter(self._search_var.get()))

    def _apply_filter(self, query: str) -> None:
        self._search_after = None
        self._filtered = sorted(
            (g for g in self._games if _matches(g, query)),
            key=lambda g: g.name.lower(),
        )
        n = len(self._filtered)
        if query.strip():
            self._title.configure(text=f"{self._base_title}  ·  найдено {n}")
        else:
            self._title.configure(text=self._base_title)

        self._clear_rows()
        self._canvas.yview_moveto(0)
        self._canvas.configure(scrollregion=(0, 0, self._content_w, n * ROW_H))
        self._toggle_empty(n == 0)
        self._schedule()

    def _refresh(self) -> None:
        log.info("list: manual refresh (force icon retry for visible rows)")
        self._force_icons = True
        self._clear_rows()
        self._schedule()

    def _toggle_empty(self, show: bool) -> None:
        if show and self._empty_item is None:
            self._empty_item = self._canvas.create_window(
                self._content_w // 2, 60, window=self._empty, anchor="n"
            )
        elif not show and self._empty_item is not None:
            self._canvas.delete(self._empty_item)
            self._empty_item = None

    # ---- прокрутка ----------------------------------------------------

    def _yview(self, *args) -> None:
        self._canvas.yview(*args)
        self._schedule()

    def _scroll_set(self, *args) -> None:
        self._scroll.set(*args)
        self._schedule()

    def _wheel(self, event) -> str:
        if event.num == 4:
            step = -2
        elif event.num == 5:
            step = 2
        else:
            step = -2 if event.delta > 0 else 2
        self._canvas.yview_scroll(step, "units")
        self._schedule()
        return "break"

    def _bind_wheel(self, widget) -> None:
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(seq, self._wheel)

    def _on_canvas_configure(self, event) -> None:
        self._content_w = max(200, event.width)
        self._canvas.configure(
            scrollregion=(0, 0, self._content_w, len(self._filtered) * ROW_H)
        )
        if self._empty_item is not None:
            self._canvas.coords(self._empty_item, self._content_w // 2, 60)
        for idx, (frame, item, icon, name) in self._rows.items():
            self._canvas.itemconfigure(item, width=self._content_w)
            name.configure(text=self._trunc(self._filtered[idx].name))
        self._schedule()

    def _schedule(self) -> None:
        if self._render_pending is None:
            self._render_pending = self.after_idle(self._do_render)

    def _do_render(self) -> None:
        self._render_pending = None
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        self._render_visible()

    # ---- виртуализация ------------------------------------------------

    def _clear_rows(self) -> None:
        for frame, item, _icon, _name in self._rows.values():
            self._canvas.delete(item)
            frame.destroy()
        self._rows.clear()

    def _render_visible(self) -> None:
        n = len(self._filtered)
        if n == 0:
            self._clear_rows()
            return
        h = self._canvas.winfo_height() or 600
        top = self._canvas.canvasy(0)
        bottom = self._canvas.canvasy(h)
        first = max(0, int(top // ROW_H) - BUFFER)
        last = min(n - 1, int(bottom // ROW_H) + BUFFER)
        force = self._force_icons
        self._force_icons = False

        for idx in list(self._rows):
            if idx < first or idx > last:
                frame, item, _icon, _name = self._rows.pop(idx)
                self._canvas.delete(item)
                frame.destroy()

        tasks: list[tuple[str, Callable]] = []
        for idx in range(first, last + 1):
            if idx not in self._rows:
                tasks.extend(self._create_row(idx))
        log.debug("list render: %d games, rows %d-%d, new tasks=%d, force=%s",
                  n, first, last, len(tasks), force)
        if tasks:
            self._icons.request_many(tasks, icons.LIST_SIZE, icons.LIST_RADIUS, force=force)

    def _trunc(self, text: str) -> str:
        max_chars = max(12, (self._content_w - 100) // 7)
        return text if len(text) <= max_chars else text[: max_chars - 1] + "…"

    def _create_row(self, index: int) -> list[tuple[str, Callable]]:
        game = self._filtered[index]
        installed = game.appid in self._installed_ids
        y = index * ROW_H

        frame = ctk.CTkFrame(
            self._canvas, fg_color=_ROW_BG, corner_radius=8, height=ROW_H - 6
        )
        frame.pack_propagate(False)

        btn = ctk.CTkButton(
            frame, text="▶", width=34, height=30,
            command=lambda g=game: launch_game(g),
        )
        btn.pack(side="right", padx=(4, 10))

        icon = None
        if icons.PIL_OK:
            icon = ctk.CTkLabel(
                frame, text="🎮", font=("", 16),
                text_color=("gray60", "gray35"), height=icons.LIST_SIZE[1], anchor="w",
            )
            icon.pack(side="top", anchor="w", padx=(12, 0), pady=(6, 0))
            icon.bind("<Button-1>", lambda _e, g=game: self._open_store(g))

        name = ctk.CTkLabel(
            frame, text=self._trunc(game.name), anchor="w", justify="left",
            font=("", 13, "bold"), height=22,
            text_color=("gray10", "gray90") if installed else ("gray40", "gray55"),
        )
        name.pack(side="top", anchor="w", fill="x", padx=(12, 0), pady=(2, 0))
        name.bind("<Button-1>", lambda _e, g=game: self._open_store(g))

        item = self._canvas.create_window(
            0, y, anchor="nw", window=frame, width=self._content_w, height=ROW_H - 6
        )
        self._rows[index] = (frame, item, icon, name)

        for w in (frame, icon, name, btn):
            if w is not None:
                self._bind_wheel(w)

        def enter(_e, g=game, f=frame):
            f.configure(fg_color=_ROW_HOVER)
            state = "" if (not self._full or g.appid in self._installed_ids) else "  ·  не установлена"
            self._footer.configure(text=f"{g.name}  ·  appid {g.appid}{state}")

        def leave(_e, f=frame):
            f.configure(fg_color=_ROW_BG)
            self._footer.configure(text="Наведите на игру, чтобы увидеть полное название")

        for w in (frame, icon, name):
            if w is not None:
                w.bind("<Enter>", enter)
                w.bind("<Leave>", leave)

        if icons.PIL_OK and icon is not None:
            def ready(img, lbl=icon, aid=game.appid):
                try:
                    if lbl.winfo_exists():
                        lbl.configure(image=img, text="")
                    else:
                        log.debug("icon %s: ready but row already recycled", aid)
                except Exception:
                    log.exception("icon %s: apply to row failed", aid)
            return [(game.appid, ready)]
        return []

    # ---- очистка -----------------------------------------------------

    def destroy(self) -> None:
        for aid in (self._render_pending, self._search_after):
            if aid is not None:
                try:
                    self.after_cancel(aid)
                except Exception:
                    pass
        self._clear_rows()
        super().destroy()
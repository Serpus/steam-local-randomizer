"""Окно «Все игры»: живой поиск, иконки над названиями, запуск."""
from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from ..i18n import plural_ru
from ..library_parser import Game
from ..launcher import launch_game
from . import icons


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
        self._render_after: str | None = None

        self.title("Вся библиотека" if self._full else "Все установленные игры")
        self.geometry("500x640")
        self.minsize(400, 460)
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
            bar,
            textvariable=self._search_var,
            placeholder_text="🔍  Поиск по названию или appid…",
            height=34,
        )
        self._search.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(bar, text="⟳", width=34, height=34, command=self._render).pack(
            side="right", padx=(6, 0)
        )

        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._search.bind("<KeyRelease>", self._on_key)
        self._search.bind("<Escape>", lambda _e: (self._search_var.set(""), self._render()))
        self.after(60, self._search.focus_set)
        self._render()

    def _on_key(self, _event=None) -> None:
        if self._render_after is not None:
            try:
                self.after_cancel(self._render_after)
            except Exception:
                pass
        self._render_after = self.after(180, self._render)

    def _render(self) -> None:
        self._render_after = None
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return

        query = self._search_var.get()
        for child in self._scroll.winfo_children():
            child.destroy()

        shown = [g for g in self._games if _matches(g, query)]
        if query.strip():
            self._title.configure(text=f"{self._base_title}  ·  найдено {len(shown)}")
        else:
            self._title.configure(text=self._base_title)

        if not shown:
            ctk.CTkLabel(
                self._scroll, text="Ничего не найдено", text_color=("gray50", "gray55")
            ).pack(pady=24)
            return

        tasks: list[tuple[str, Callable]] = []
        for game in sorted(shown, key=lambda g: g.name.lower()):
            icon_label = self._build_row(game)
            if icons.PIL_OK and icon_label is not None:
                def ready(img, lbl=icon_label):
                    try:
                        if self.winfo_exists() and lbl.winfo_exists():
                            lbl.configure(image=img, text="")
                    except Exception:
                        pass
                tasks.append((game.appid, ready))

        self._icons.request_many(tasks, icons.LIST_SIZE, icons.LIST_RADIUS)

    def _build_row(self, game: Game):
        row = ctk.CTkFrame(self._scroll, fg_color="transparent")
        row.pack(fill="x", pady=4)

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True, padx=(6, 0))

        icon_label = None
        if icons.PIL_OK:
            icon_label = ctk.CTkLabel(
                left,
                text="🎮",
                font=("", 18),
                text_color=("gray60", "gray35"),
                height=icons.LIST_SIZE[1],
                anchor="w",
            )
            icon_label.pack(anchor="w")
            icon_label.bind("<Button-1>", lambda _e, g=game: self._open_store(g))

        text = game.name
        if self._full and game.appid not in self._installed_ids:
            text += "   ·  не установлена"

        name = ctk.CTkLabel(
            left, text=text, anchor="w", justify="left", wraplength=340, cursor="hand2"
        )
        name.pack(anchor="w", fill="x")
        name.bind("<Button-1>", lambda _e, g=game: self._open_store(g))

        ctk.CTkButton(
            row, text="▶", width=32, height=26, command=lambda g=game: launch_game(g)
        ).pack(side="right", padx=(6, 4))

        return icon_label
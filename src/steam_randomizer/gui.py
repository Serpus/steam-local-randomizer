"""CustomTkinter GUI — оболочка приложения: раскладка, рулетка, оркестрация.

Компоненты вынесены в подпакет ui/:
  ui/icons.py        — IconService (кэш + фоновая загрузка иконок)
  ui/games_window.py — AllGamesWindow (окно «Все игры» с поиском)
  ui/loading.py      — LoadingIndicator (точки + прогресс-бар)
"""
from __future__ import annotations

import random
import threading
import webbrowser
from collections.abc import Callable

import customtkinter as ctk

from . import __version__
from . import settings as app_settings
from .full_library import find_all_owned_games
from .game_filter import hide_unnamed_games
from .i18n import plural_ru
from .library_parser import Game, find_installed_games
from .launcher import launch_game
from .randomizer import filter_games, pick_random_game
from .steam_api import last_fetch_online
from .steam_locator import SteamNotFoundError, find_steam_path
from .ui import icons
from .ui.games_window import AllGamesWindow
from .ui.icons import IconService
from .ui.loading import LoadingIndicator
from .ui.blacklist_window import BlacklistWindow

_SPIN_DELAYS: tuple[int, ...] = (
    40, 40, 45, 50, 55, 60, 70, 80, 90, 100,
    115, 130, 150, 175, 200, 230, 265, 300, 345, 400, 460, 530,
)

_STORE_URL = "https://store.steampowered.com/app/{appid}/"


class SteamRandomizerApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Steam Local Randomizer")
        self.geometry("560x620")
        self.minsize(500, 560)

        self.games: list[Game] = []
        self._installed_games: list[Game] = []
        self._all_owned_games: list[Game] = []
        self._all_owned_loaded = False
        self._use_full_library = False
        self.current_game: Game | None = None
        self.rng = random.Random()

        self._rolling = False
        self._spin_after_id: str | None = None
        self._on_finish: Callable[[], None] | None = None
        self._icon_req = 0

        self._roll_pool: list[Game] = []
        self._all_games_win = None
        self._blacklist_win = None

        self._icons = IconService(self._safe_after)

        self._build_ui()
        self._loader = LoadingIndicator(self, self.status, self.progress, before=self.result)
        self.after(50, self._start_initial_loading)

    # ---- UI ----------------------------------------------------------

    def _build_ui(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(18, 4))

        self.status = ctk.CTkLabel(
            header, text="Ищем библиотеку Steam", font=("", 13), anchor="w"
        )
        self.status.pack(side="left")

        self.show_all_btn = ctk.CTkButton(
            header,
            text="📋 Все игры",
            width=110,
            height=28,
            fg_color="transparent",
            border_width=1,
            hover_color=("gray70", "gray30"),
            command=self._show_all_games,
            state="disabled",
        )
        self.show_all_btn.pack(side="right")

        self.blacklist_btn = ctk.CTkButton(
            header,
            text="⛔",
            width=34,
            height=28,
            fg_color="transparent",
            border_width=1,
            hover_color=("gray70", "gray30"),
            command=self._open_blacklist,
        )
        self.blacklist_btn.pack(side="right", padx=(0, 6))

        options_row = ctk.CTkFrame(self, fg_color="transparent")
        options_row.pack(fill="x", padx=22, pady=(4, 0))

        self.full_library_var = ctk.BooleanVar(value=False)
        self.full_library_check = ctk.CTkCheckBox(
            options_row,
            text="Вся библиотека (включая не установленные)",
            variable=self.full_library_var,
            command=self._on_full_library_toggle,
            state="disabled",
            height=24,
            checkbox_width=18,
            checkbox_height=18,
            font=("", 12),
        )
        self.full_library_check.pack(side="left")

        self.progress = ctk.CTkProgressBar(self, mode="indeterminate", height=4)
        self.progress.pack(fill="x", padx=22, pady=(6, 0))
        self.progress.start()

        if icons.PIL_OK:
            self.result_icon = ctk.CTkLabel(
                self,
                text="🎮",
                font=("", 44),
                text_color=("gray60", "gray35"),
                height=icons.RESULT_SIZE[1],
            )
            self.result_icon.pack(pady=(14, 0))
            self.result_icon.bind("<Button-1>", self._on_result_clicked)

        self.result = ctk.CTkLabel(
            self,
            text="Нажмите «Крутить!»",
            font=("", 24, "bold"),
            wraplength=500,
            justify="center",
        )
        self.result.pack(pady=(10, 18), expand=True)
        self.result.bind("<Button-1>", self._on_result_clicked)

        # Кнопка «В чёрный список» — появляется только после ролла.
        # Пока игра не выбрана или в списке, pack_forget() держит её невидимой.
        self.blacklist_game_btn = ctk.CTkButton(
            self,
            text="🚫  В чёрный список",
            height=30,
            width=240,
            fg_color="transparent",
            border_width=1,
            hover_color=("gray70", "gray30"),
            font=("", 12),
            command=self._toggle_current_blacklist,
        )
        # НЕ вызываем .pack() здесь — только по завершении ролла.

        self.roll_btn = ctk.CTkButton(
            self,
            text="🎲  Крутить!",
            height=52,
            font=("", 17, "bold"),
            command=self._roll,
            state="disabled",
        )
        self.roll_btn.pack(fill="x", padx=22, pady=(0, 10))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=(0, 18))

        self.launch_btn = ctk.CTkButton(
            row, text="▶  Запустить", command=self._launch, state="disabled"
        )
        self.launch_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.roll_launch_btn = ctk.CTkButton(
            row,
            text="🎲▶  Крутить и запустить",
            command=self._roll_and_launch,
            state="disabled",
        )
        self.roll_launch_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))

        ctk.CTkLabel(
            self,
            text=f"v{__version__}",
            font=("", 11),
            text_color=("gray50", "gray60"),
        ).pack(side="bottom", anchor="e", padx=14, pady=(0, 6))

    # ---- кнопка чёрного списка у результата --------------------------

    def _update_blacklist_btn(self) -> None:
        """Показать/скрыть кнопку и обновить её текст по текущей игре."""
        if self.current_game is None:
            try:
                self.blacklist_game_btn.pack_forget()
            except Exception:
                pass
            return

        in_bl = self.current_game.appid in app_settings.get_blacklist()
        self.blacklist_game_btn.configure(
            text=("✅  Убрать из чёрного списка" if in_bl else "🚫  В чёрный список")
        )
        try:
            self.blacklist_game_btn.pack(pady=(0, 12), before=self.roll_btn)
        except Exception:
            pass

    def _toggle_current_blacklist(self) -> None:
        if self.current_game is None:
            return
        self._toggle_blacklist(self.current_game)

    # ---- иконка результата -------------------------------------------

    def _set_result_placeholder(self, glyph: str = "🎮") -> None:
        if icons.PIL_OK:
            self.result_icon.configure(image=None, text=glyph)

    def _show_result_icon(self, appid: str, *, allow_fetch: bool) -> None:
        if not icons.PIL_OK:
            return
        img = self._icons.cached(appid, icons.RESULT_SIZE, icons.RESULT_RADIUS)
        if img is not None:
            self.result_icon.configure(image=img, text="")
            return
        self.result_icon.configure(image=None, text="")
        if not allow_fetch:
            return
        self._icon_req += 1
        req = self._icon_req

        def ready(img) -> None:
            if req != self._icon_req:
                return
            if self.current_game is None or self.current_game.appid != appid:
                return
            self.result_icon.configure(image=img, text="")

        self._icons.request(appid, icons.RESULT_SIZE, icons.RESULT_RADIUS, ready)

    # ---- открытие страницы игры в Steam -----------------------------

    def _on_result_clicked(self, _event=None) -> None:
        if self.current_game is not None:
            self._open_store_page(self.current_game)

    def _open_store_page(self, game: Game) -> None:
        try:
            webbrowser.open(_STORE_URL.format(appid=game.appid))
        except Exception:  # noqa: BLE001
            pass

    # ---- загрузка ----------------------------------------------------

    def _safe_after(self, func, *args) -> None:
        def wrapper() -> None:
            try:
                func(*args)
            except Exception:
                pass
        try:
            self.after(0, wrapper)
        except Exception:
            pass

    def _start_initial_loading(self) -> None:
        self._loader.start("Ищем библиотеку Steam")
        threading.Thread(target=self._load_games_bg, daemon=True).start()

    def _load_games_bg(self) -> None:
        try:
            steam_path = find_steam_path()
            all_games = find_installed_games(steam_path)
        except SteamNotFoundError as exc:
            self._safe_after(self._on_load_done, None, str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._safe_after(self._on_load_done, None, f"Ошибка чтения библиотеки: {exc}")
            return
        self._safe_after(self._on_load_done, all_games, None)

    def _on_load_done(self, all_games: list[Game] | None, error: str | None) -> None:
        self._loader.stop()
        if error is not None:
            self.status.configure(text=error)
            return
        assert all_games is not None
        self._installed_games = filter_games(all_games)
        if not self._installed_games:
            self.status.configure(text="В библиотеке не найдено ни одной установленной игры.")
            return
        self._apply_pool(self._installed_games)
        self.show_all_btn.configure(state="normal")
        self.roll_btn.configure(state="normal")
        self.roll_launch_btn.configure(state="normal")
        self.full_library_check.configure(state="normal")

    def _apply_pool(self, pool: list[Game]) -> None:
        self.games = pool
        count = len(self.games)
        word = plural_ru(count, "игра", "игры", "игр")
        suffix = " (вся библиотека)" if self._use_full_library else ""
        self.status.configure(text=f"{count} {word} в библиотеке{suffix}")

        self.current_game = None
        self.result.configure(
            text="Нажмите «Крутить!»", text_color=("gray10", "gray95"), cursor="arrow"
        )
        self.launch_btn.configure(state="disabled")
        self._icon_req += 1
        self._set_result_placeholder()
        self._update_blacklist_btn()

    # ---- чекбокс «Вся библиотека» ------------------------------------

    def _on_full_library_toggle(self) -> None:
        if self._rolling or self._loader.active:
            self.full_library_var.set(self._use_full_library)
            return
        if self.full_library_var.get():
            if self._all_owned_loaded:
                self._use_full_library = True
                self._apply_pool(self._all_owned_games)
            else:
                self._load_full_library_async()
        else:
            self._use_full_library = False
            self._apply_pool(self._installed_games)

    def _load_full_library_async(self) -> None:
        self.full_library_check.configure(state="disabled")
        self.roll_btn.configure(state="disabled")
        self.roll_launch_btn.configure(state="disabled")
        self.show_all_btn.configure(state="disabled")
        self._loader.start("Загружаем полную библиотеку Steam")
        threading.Thread(target=self._load_full_library_bg, daemon=True).start()

    def _load_full_library_bg(self) -> None:
        try:
            steam_path = find_steam_path()
            games = find_all_owned_games(steam_path, on_progress=self._on_full_lib_progress)
            self._safe_after(self._on_full_library_loaded, games, None)
        except Exception as exc:  # noqa: BLE001
            self._safe_after(self._on_full_library_loaded, None, str(exc))

    def _on_full_lib_progress(self, done: int, total: int) -> None:
        self._safe_after(self._loader.set_message, f"Загружаем названия игр: {done} из {total}")

    def _on_full_library_loaded(self, games: list[Game] | None, error: str | None) -> None:
        self._loader.stop()
        if error is not None:
            self.status.configure(text=f"Ошибка загрузки библиотеки: {error}")
            self.full_library_var.set(False)
            self._use_full_library = False
            self._apply_pool(self._installed_games)
            self._re_enable_controls()
            return
        assert games is not None
        if not games:
            self.status.configure(
                text="Не удалось получить список всех игр (нет localconfig.vdf или appinfo.vdf)."
            )
            self.full_library_var.set(False)
            self._use_full_library = False
            self._re_enable_controls()
            return

        games = hide_unnamed_games(games, online=last_fetch_online())
        self._all_owned_games = games
        self._all_owned_loaded = True
        self._use_full_library = True
        self._apply_pool(games)
        self._re_enable_controls()

    def _re_enable_controls(self) -> None:
        self.full_library_check.configure(state="normal")
        if self.games:
            self.roll_btn.configure(state="normal")
            self.roll_launch_btn.configure(state="normal")
            self.show_all_btn.configure(state="normal")

    # ---- чёрный список ------------------------------------------------

    def _open_blacklist(self) -> None:
        if self._blacklist_win is not None:
            try:
                if self._blacklist_win.winfo_exists():
                    self._blacklist_win.focus()
                    return
            except Exception:
                self._blacklist_win = None

        games = self._installed_games
        if self._use_full_library and self._all_owned_games:
            games = self._all_owned_games

        self._blacklist_win = BlacklistWindow(
            self,
            games=games,
            on_blacklist_changed=self._on_blacklist_changed,
        )

    def _on_blacklist_changed(self, new_blacklist: set[str]) -> None:
        """Синхронизация: обновляем окно «Все игры» если оно открыто."""
        if self._all_games_win is not None:
            try:
                if self._all_games_win.winfo_exists():
                    self._all_games_win.update_blacklist(new_blacklist)
            except Exception:
                pass

    def _get_roll_pool(self) -> list[Game]:
        """Пул для рулетки с учётом чёрного списка."""
        pool = self.games
        if app_settings.is_use_blacklist():
            bl = app_settings.get_blacklist()
            pool = [g for g in pool if g.appid not in bl]
        return pool

    def _toggle_blacklist(self, game: Game) -> None:
        app_settings.toggle_blacklist(game.appid)
        new_bl = app_settings.get_blacklist()
        # Синхронизация: обновляем окно «Все игры»
        if self._all_games_win is not None:
            try:
                if self._all_games_win.winfo_exists():
                    self._all_games_win.update_blacklist(new_bl)
            except Exception:
                pass
        # Синхронизация: обновляем окно ЧС
        if self._blacklist_win is not None:
            try:
                if self._blacklist_win.winfo_exists():
                    self._blacklist_win.update_blacklist(new_bl)
            except Exception:
                pass
        # Синхронизация: обновляем кнопку на главном экране
        self._update_blacklist_btn()

    def _clear_blacklist(self) -> None:
        app_settings.clear_blacklist()
        if self._all_games_win is not None:
            try:
                if self._all_games_win.winfo_exists():
                    self._all_games_win.update_blacklist(set())
            except Exception:
                pass
        if self._blacklist_win is not None:
            try:
                if self._blacklist_win.winfo_exists():
                    self._blacklist_win.update_blacklist(set())
            except Exception:
                pass
        self._update_blacklist_btn()

    # ---- рулетка ----------------------------------------------------

    def _roll(self, on_finish: Callable[[], None] | None = None) -> None:
        if self._rolling or self._loader.active or not self.games:
            return
        pool = self._get_roll_pool()
        if not pool:
            self.status.configure(text="Все игры в чёрном списке — нечего крутить.")
            return

        self._rolling = True
        self._on_finish = on_finish
        self.current_game = None
        self._roll_pool = pool
        self._icon_req += 1
        self._set_result_placeholder(glyph="")
        self._update_blacklist_btn()

        self.roll_btn.configure(state="disabled")
        self.roll_launch_btn.configure(state="disabled")
        self.launch_btn.configure(state="disabled")
        self.full_library_check.configure(state="disabled")
        self.result.configure(text_color=("gray30", "gray60"), cursor="arrow")
        self._spin(step=0)

    def _spin(self, step: int) -> None:
        if step >= len(_SPIN_DELAYS):
            game = pick_random_game(self._roll_pool, self.rng)
            if game is not None:
                self.current_game = game
                self.result.configure(
                    text=game.name, text_color=("gray10", "gray95"), cursor="hand2"
                )
                self._show_result_icon(game.appid, allow_fetch=True)
            self._finish_roll()
            return
        flashed = self.rng.choice(self._roll_pool)
        self.result.configure(text=flashed.name)
        self._show_result_icon(flashed.appid, allow_fetch=False)
        self._spin_after_id = self.after(_SPIN_DELAYS[step], lambda: self._spin(step + 1))

    def _finish_roll(self) -> None:
        self._spin_after_id = None
        self._rolling = False
        self.roll_btn.configure(state="normal")
        self.roll_launch_btn.configure(state="normal")
        self.full_library_check.configure(state="normal")
        if self.current_game is not None:
            self.launch_btn.configure(state="normal")
        self._update_blacklist_btn()
        cb = self._on_finish
        self._on_finish = None
        if cb is not None:
            cb()

    def _launch(self) -> None:
        if self.current_game is not None:
            launch_game(self.current_game)

    def _roll_and_launch(self) -> None:
        self._roll(on_finish=self._launch)

    # ---- окно «Все игры» --------------------------------------------

    def _show_all_games(self) -> None:
        if not self.games:
            return
        if self._all_games_win is not None:
            try:
                if self._all_games_win.winfo_exists():
                    self._all_games_win.focus()
                    return
            except Exception:
                self._all_games_win = None

        self._all_games_win = AllGamesWindow(
            self,
            games=self.games,
            installed_ids={g.appid for g in self._installed_games},
            use_full_library=self._use_full_library,
            icon_service=self._icons,
            on_open_store=self._open_store_page,
            blacklist=app_settings.get_blacklist(),
            on_toggle_blacklist=self._toggle_blacklist,
            # on_clear_blacklist убран — кнопка очистки только в окне ЧС
        )

    # ---- очистка -----------------------------------------------------

    def destroy(self) -> None:
        self._loader.stop()
        if self._spin_after_id is not None:
            try:
                self.after_cancel(self._spin_after_id)
            except Exception:
                pass
        self._all_games_win = None
        self._blacklist_win = None
        super().destroy()


def main() -> int:
    app = SteamRandomizerApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
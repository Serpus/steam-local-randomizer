"""CustomTkinter GUI for steam-local-randomizer."""
from __future__ import annotations

import queue
import random
import threading
import webbrowser
from collections.abc import Callable
from pathlib import Path

import customtkinter as ctk

try:
    from PIL import Image, ImageDraw
    _PIL_OK = True
except ImportError:  # Pillow не установлен — иконки отключены, приложение работает
    _PIL_OK = False

from . import __version__
from .full_library import find_all_owned_games
from .game_filter import hide_unnamed_games
from .game_icons import cached_icon, fetch_icon
from .i18n import plural_ru
from .library_parser import Game, find_installed_games
from .launcher import launch_game
from .randomizer import filter_games, pick_random_game
from .steam_api import last_fetch_online
from .steam_locator import SteamNotFoundError, find_steam_path

_SPIN_DELAYS: tuple[int, ...] = (
    40, 40, 45, 50, 55, 60, 70, 80, 90, 100,
    115, 130, 150, 175, 200, 230, 265, 300, 345, 400, 460, 530,
)

_STORE_URL = "https://store.steampowered.com/app/{appid}/"

_RESULT_ICON_SIZE = (320, 150)
_LIST_ICON_SIZE = (112, 52)
_ICON_WORKERS = 3


def _make_icon_image(path: Path, size: tuple[int, int], radius: int) -> ctk.CTkImage | None:
    """jpg -> скруглённый CTkImage (2x для HiDPI). Только главный поток Tk."""
    if not _PIL_OK:
        return None
    try:
        img = Image.open(path).convert("RGB")
        img = img.resize((size[0] * 2, size[1] * 2), Image.Resampling.LANCZOS)
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, img.size[0] - 1, img.size[1] - 1), radius=radius * 2, fill=255
        )
        img.putalpha(mask)
        return ctk.CTkImage(light_image=img, dark_image=img, size=size)
    except Exception:
        return None


def _game_matches(game: Game, query: str) -> bool:
    """Поиск по подстроке названия (без регистра) или по appid."""
    q = query.strip().lower()
    if not q:
        return True
    return q in game.name.lower() or q in game.appid


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

        self._loading = True
        self._loading_after_id: str | None = None
        self._loading_base_msg = "Ищем библиотеку Steam"

        self._icon_mem: dict[tuple[str, tuple[int, int]], ctk.CTkImage] = {}
        self._icon_req = 0

        self._build_ui()
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

        # Иконка игры — над названием. Место зарезервировано, чтобы
        # интерфейс не прыгал при появлении картинки.
        if _PIL_OK:
            self.result_icon = ctk.CTkLabel(
                self,
                text="🎮",
                font=("", 44),
                text_color=("gray60", "gray35"),
                height=_RESULT_ICON_SIZE[1],
            )
            self.result_icon.pack(pady=(14, 0))
            self.result_icon.bind("<Button-1>", self._on_result_clicked)

        # Результат — кликабельный: открывает страницу игры в Steam.
        self.result = ctk.CTkLabel(
            self,
            text="Нажмите «Крутить!»",
            font=("", 24, "bold"),
            wraplength=500,
            justify="center",
        )
        self.result.pack(pady=(10, 18), expand=True)
        self.result.bind("<Button-1>", self._on_result_clicked)

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

        # Версия — только в правом нижнем углу.
        version_label = ctk.CTkLabel(
            self,
            text=f"v{__version__}",
            font=("", 11),
            text_color=("gray50", "gray60"),
        )
        version_label.pack(side="bottom", anchor="e", padx=14, pady=(0, 6))

    # ---- иконки ------------------------------------------------------

    def _show_icon(self, appid: str | None, *, allow_fetch: bool) -> None:
        """Главный поток: показать иконку над названием (мгновенно из кэша)."""
        if not _PIL_OK:
            return
        if appid is None:
            self.result_icon.configure(image=None, text="🎮")
            return

        key = (appid, _RESULT_ICON_SIZE)
        img = self._icon_mem.get(key)
        if img is None:
            path = cached_icon(appid)
            if path is not None:
                img = _make_icon_image(path, _RESULT_ICON_SIZE, 10)
                if img is not None:
                    self._icon_mem[key] = img

        if img is not None:
            self.result_icon.configure(image=img, text="")
            return

        self.result_icon.configure(image=None, text="")
        if allow_fetch:
            self._icon_req += 1
            req = self._icon_req
            threading.Thread(
                target=self._fetch_result_icon_bg, args=(appid, req), daemon=True
            ).start()

    def _fetch_result_icon_bg(self, appid: str, req: int) -> None:
        path = fetch_icon(appid)
        if path is not None:
            self._safe_after(self._apply_result_icon, appid, req, path)

    def _apply_result_icon(self, appid: str, req: int, path: Path) -> None:
        if not _PIL_OK:
            return
        if req != self._icon_req:
            return
        if self.current_game is None or self.current_game.appid != appid:
            return
        key = (appid, _RESULT_ICON_SIZE)
        img = self._icon_mem.get(key) or _make_icon_image(path, _RESULT_ICON_SIZE, 10)
        if img is None:
            return
        self._icon_mem[key] = img
        self.result_icon.configure(image=img, text="")

    def _list_icon_worker(self, q: queue.Queue, win: ctk.CTkToplevel) -> None:
        while True:
            try:
                appid, label = q.get_nowait()
            except queue.Empty:
                return
            path = fetch_icon(appid)
            if path is not None:
                self._safe_after(self._apply_list_icon, appid, label, path, win)

    def _apply_list_icon(self, appid: str, label, path: Path, win) -> None:
        if not _PIL_OK:
            return
        try:
            if not win.winfo_exists() or not label.winfo_exists():
                return
        except Exception:
            return
        key = (appid, _LIST_ICON_SIZE)
        img = self._icon_mem.get(key) or _make_icon_image(path, _LIST_ICON_SIZE, 6)
        if img is None:
            return
        self._icon_mem[key] = img
        label.configure(image=img, text="")

    # ---- открытие страницы игры в Steam -----------------------------

    def _on_result_clicked(self, _event=None) -> None:
        if self.current_game is not None:
            self._open_store_page(self.current_game)

    def _open_store_page(self, game: Game) -> None:
        url = _STORE_URL.format(appid=game.appid)
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass

    # ---- загрузка ----------------------------------------------------

    def _start_initial_loading(self) -> None:
        self._start_loading("Ищем библиотеку Steam")
        threading.Thread(target=self._load_games_bg, daemon=True).start()

    def _start_loading(self, message: str) -> None:
        self._loading = True
        self._loading_base_msg = message
        try:
            self.progress.pack(fill="x", padx=22, pady=(6, 0), before=self.result)
            self.progress.start()
        except Exception:
            pass
        self._animate_loading_dots(0)

    def _animate_loading_dots(self, dots: int) -> None:
        if not self._loading:
            return
        self.status.configure(text=self._loading_base_msg + "." * (dots % 4))
        self._loading_after_id = self.after(
            350, lambda: self._animate_loading_dots(dots + 1)
        )

    def _stop_loading(self) -> None:
        self._loading = False
        if self._loading_after_id is not None:
            try:
                self.after_cancel(self._loading_after_id)
            except Exception:
                pass
            self._loading_after_id = None
        try:
            self.progress.stop()
            self.progress.pack_forget()
        except Exception:
            pass

    def _load_games_bg(self) -> None:
        try:
            steam_path = find_steam_path()
            all_games = find_installed_games(steam_path)
        except SteamNotFoundError as exc:
            self._safe_after(self._on_load_done, None, str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._safe_after(
                self._on_load_done, None, f"Ошибка чтения библиотеки: {exc}"
            )
            return
        self._safe_after(self._on_load_done, all_games, None)

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

    def _on_load_done(self, all_games: list[Game] | None, error: str | None) -> None:
        self._stop_loading()

        if error is not None:
            self.status.configure(text=error)
            return

        assert all_games is not None
        self._installed_games = filter_games(all_games)
        if not self._installed_games:
            self.status.configure(
                text="В библиотеке не найдено ни одной установленной игры."
            )
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
            text="Нажмите «Крутить!»",
            text_color=("gray10", "gray95"),
            cursor="arrow",
        )
        self.launch_btn.configure(state="disabled")
        self._icon_req += 1
        self._show_icon(None, allow_fetch=False)

    # ---- чекбокс «Вся библиотека» ------------------------------------

    def _on_full_library_toggle(self) -> None:
        if self._rolling or self._loading:
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

        self._start_loading("Загружаем полную библиотеку Steam")
        threading.Thread(target=self._load_full_library_bg, daemon=True).start()

    def _load_full_library_bg(self) -> None:
        try:
            steam_path = find_steam_path()
            games = find_all_owned_games(steam_path)
            self._safe_after(self._on_full_library_loaded, games, None)
        except Exception as exc:  # noqa: BLE001
            self._safe_after(self._on_full_library_loaded, None, str(exc))

    def _on_full_library_loaded(
        self, games: list[Game] | None, error: str | None
    ) -> None:
        self._stop_loading()

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
                text="Не удалось получить список всех игр "
                     "(нет localconfig.vdf или appinfo.vdf)."
            )
            self.full_library_var.set(False)
            self._use_full_library = False
            self._re_enable_controls()
            return

        # Прячем безымянные демо/удалённые записи только если интернет
        # доступен и остальные названия действительно получены.
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

    # ---- рулетка ----------------------------------------------------

    def _roll(self, on_finish: Callable[[], None] | None = None) -> None:
        if self._rolling or self._loading or not self.games:
            return

        self._rolling = True
        self._on_finish = on_finish
        self.current_game = None
        self._icon_req += 1
        if _PIL_OK:
            self.result_icon.configure(image=None, text="")

        self.roll_btn.configure(state="disabled")
        self.roll_launch_btn.configure(state="disabled")
        self.launch_btn.configure(state="disabled")
        self.full_library_check.configure(state="disabled")
        self.result.configure(text_color=("gray30", "gray60"), cursor="arrow")

        self._spin(step=0)

    def _spin(self, step: int) -> None:
        total = len(_SPIN_DELAYS)
        if step >= total:
            game = pick_random_game(self.games, self.rng)
            if game is not None:
                self.current_game = game
                self.result.configure(
                    text=game.name,
                    text_color=("gray10", "gray95"),
                    cursor="hand2",
                )
                self._show_icon(game.appid, allow_fetch=True)
            self._finish_roll()
            return

        flashed = self.rng.choice(self.games)
        self.result.configure(text=flashed.name)
        self._show_icon(flashed.appid, allow_fetch=False)
        self._spin_after_id = self.after(
            _SPIN_DELAYS[step], lambda: self._spin(step + 1)
        )

    def _finish_roll(self) -> None:
        self._spin_after_id = None
        self._rolling = False

        self.roll_btn.configure(state="normal")
        self.roll_launch_btn.configure(state="normal")
        self.full_library_check.configure(state="normal")
        if self.current_game is not None:
            self.launch_btn.configure(state="normal")

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

        win = ctk.CTkToplevel(self)
        win.title(
            "Вся библиотека" if self._use_full_library else "Все установленные игры"
        )
        win.geometry("500x640")
        win.minsize(400, 460)
        win.transient(self)
        win.after(10, win.grab_set)

        count = len(self.games)
        word = plural_ru(count, "игра", "игры", "игр")
        if self._use_full_library:
            base_title = f"Вся библиотека: {count} {word}"
        else:
            base_title = f"Установлено {count} {word}"

        title_lbl = ctk.CTkLabel(win, text=base_title, font=("", 14, "bold"))
        title_lbl.pack(pady=(14, 6))

        search_var = ctk.StringVar(value="")
        search = ctk.CTkEntry(
            win,
            textvariable=search_var,
            placeholder_text="🔍  Поиск по названию или appid…",
            height=34,
        )
        search.pack(fill="x", padx=12, pady=(0, 8))

        scroll = ctk.CTkScrollableFrame(win)
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        installed_ids = {g.appid for g in self._installed_games}
        render_after: list[str | None] = [None]

        def render() -> None:
            render_after[0] = None
            try:
                if not win.winfo_exists():
                    return
            except Exception:
                return

            query = search_var.get()
            for child in scroll.winfo_children():
                child.destroy()

            shown = [g for g in self.games if _game_matches(g, query)]
            if query.strip():
                title_lbl.configure(text=f"{base_title}  ·  найдено {len(shown)}")
            else:
                title_lbl.configure(text=base_title)

            if not shown:
                ctk.CTkLabel(
                    scroll,
                    text="Ничего не найдено",
                    text_color=("gray50", "gray55"),
                ).pack(pady=24)
                return

            icon_queue: queue.Queue = queue.Queue()
            enqueued: set[str] = set()

            for game in sorted(shown, key=lambda g: g.name.lower()):
                row = ctk.CTkFrame(scroll, fg_color="transparent")
                row.pack(fill="x", pady=4)

                left = ctk.CTkFrame(row, fg_color="transparent")
                left.pack(side="left", fill="x", expand=True, padx=(6, 0))

                # Иконка — над названием, как в главном окне.
                icon_label = ctk.CTkLabel(
                    left,
                    text="🎮" if _PIL_OK else "",
                    font=("", 18),
                    text_color=("gray60", "gray35"),
                    height=_LIST_ICON_SIZE[1] if _PIL_OK else 0,
                    anchor="w",
                )
                if _PIL_OK:
                    icon_label.pack(anchor="w")
                    icon_label.bind(
                        "<Button-1>", lambda _e, g=game: self._open_store_page(g)
                    )

                label_text = game.name
                if self._use_full_library and game.appid not in installed_ids:
                    label_text += "   ·  не установлена"

                name_label = ctk.CTkLabel(
                    left,
                    text=label_text,
                    anchor="w",
                    justify="left",
                    wraplength=340,
                    cursor="hand2",
                )
                name_label.pack(anchor="w", fill="x")
                name_label.bind(
                    "<Button-1>", lambda _e, g=game: self._open_store_page(g)
                )

                ctk.CTkButton(
                    row,
                    text="▶",
                    width=32,
                    height=26,
                    command=lambda g=game: launch_game(g),
                ).pack(side="right", padx=(6, 4))

                if _PIL_OK:
                    key = (game.appid, _LIST_ICON_SIZE)
                    if key in self._icon_mem:
                        icon_label.configure(image=self._icon_mem[key], text="")
                    elif game.appid not in enqueued:
                        enqueued.add(game.appid)
                        icon_queue.put((game.appid, icon_label))

            if _PIL_OK and not icon_queue.empty():
                for _ in range(_ICON_WORKERS):
                    threading.Thread(
                        target=self._list_icon_worker,
                        args=(icon_queue, win),
                        daemon=True,
                    ).start()

        def on_key(_event=None) -> None:
            if render_after[0] is not None:
                try:
                    win.after_cancel(render_after[0])
                except Exception:
                    pass
            render_after[0] = win.after(180, render)

        search.bind("<KeyRelease>", on_key)
        search.bind("<Escape>", lambda _e: (search_var.set(""), render()))
        win.after(60, search.focus_set)

        render()

    # ---- очистка -----------------------------------------------------

    def destroy(self) -> None:
        self._loading = False
        for after_id in (self._spin_after_id, self._loading_after_id):
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
                except Exception:
                    pass
        super().destroy()


def main() -> int:
    app = SteamRandomizerApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""CustomTkinter GUI for steam-local-randomizer."""
from __future__ import annotations

import random
import threading
from collections.abc import Callable

import customtkinter as ctk

from . import __version__
from .full_library import find_all_owned_games
from .i18n import plural_ru
from .library_parser import Game, find_installed_games
from .launcher import launch_game
from .randomizer import filter_games, pick_random_game
from .steam_locator import SteamNotFoundError, find_steam_path


# Задержки (мс) между кадрами анимации «рулетки».
_SPIN_DELAYS: tuple[int, ...] = (
    40, 40, 45, 50, 55, 60, 70, 80, 90, 100,
    115, 130, 150, 175, 200, 230, 265, 300, 345, 400, 460, 530,
)


class SteamRandomizerApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Steam Local Randomizer")
        self.geometry("560x460")
        self.minsize(480, 400)

        # --- Данные ---
        self.games: list[Game] = []               # текущий активный пул
        self._installed_games: list[Game] = []    # только установленные
        self._all_owned_games: list[Game] = []    # вся библиотека (кэш)
        self._all_owned_loaded = False
        self._use_full_library = False
        self.current_game: Game | None = None
        self.rng = random.Random()

        # --- Состояние UI ---
        self._rolling = False
        self._spin_after_id: str | None = None
        self._on_finish: Callable[[], None] | None = None

        self._loading = True
        self._loading_after_id: str | None = None
        self._loading_base_msg = "Ищем библиотеку Steam"

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

        # Чекбокс «Вся библиотека» — строка под header, чтобы не сжимать кнопку.
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

        # Индикатор загрузки.
        self.progress = ctk.CTkProgressBar(self, mode="indeterminate", height=4)
        self.progress.pack(fill="x", padx=22, pady=(6, 0))
        self.progress.start()

        # Результат.
        self.result = ctk.CTkLabel(
            self,
            text="Нажмите «Крутить!»",
            font=("", 24, "bold"),
            wraplength=500,
            justify="center",
        )
        self.result.pack(pady=28, expand=True)

        # Кнопка рулетки.
        self.roll_btn = ctk.CTkButton(
            self,
            text="🎲  Крутить!",
            height=52,
            font=("", 17, "bold"),
            command=self._roll,
            state="disabled",
        )
        self.roll_btn.pack(fill="x", padx=22, pady=(0, 10))

        # Нижний ряд.
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

        # Версия в правом нижнем углу.
        version_label = ctk.CTkLabel(
            self,
            text=f"v{__version__}",
            font=("", 11),
            text_color=("gray50", "gray60"),
        )
        version_label.pack(side="bottom", anchor="e", padx=14, pady=(0, 6))

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
        """Работает в фоновом потоке — не трогает tkinter напрямую."""
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

        # Сбрасываем текущий выбор — иначе запуск уведёт в несуществующую игру.
        self.current_game = None
        self.result.configure(
            text="Нажмите «Крутить!»", text_color=("gray10", "gray95")
        )
        self.launch_btn.configure(state="disabled")

    # ---- чекбокс «Вся библиотека» ------------------------------------

    def _on_full_library_toggle(self) -> None:
        if self._rolling or self._loading:
            # Пока крутится рулетка или идёт загрузка — не переключаем.
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
            # НЕ кэшируем пустой результат — пользователь может исправить
            # ситуацию (обновить Steam, войти в аккаунт) и попробовать снова.
            self.status.configure(
                text="Не удалось получить список всех игр "
                     "(нет localconfig.vdf или appinfo.vdf)."
            )
            self.full_library_var.set(False)
            self._use_full_library = False
            self._re_enable_controls()
            return

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

    # ---- анимация рулетки --------------------------------------------

    def _roll(self, on_finish: Callable[[], None] | None = None) -> None:
        if self._rolling or self._loading or not self.games:
            return

        self._rolling = True
        self._on_finish = on_finish
        self.current_game = None

        self.roll_btn.configure(state="disabled")
        self.roll_launch_btn.configure(state="disabled")
        self.launch_btn.configure(state="disabled")
        self.full_library_check.configure(state="disabled")
        self.result.configure(text_color=("gray30", "gray60"))

        self._spin(step=0)

    def _spin(self, step: int) -> None:
        total = len(_SPIN_DELAYS)
        if step >= total:
            game = pick_random_game(self.games, self.rng)
            if game is not None:
                self.current_game = game
                self.result.configure(
                    text=game.name, text_color=("gray10", "gray95")
                )
            self._finish_roll()
            return

        self.result.configure(text=self.rng.choice(self.games).name)
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

    # ---- окно «Все игры» ---------------------------------------------

    def _show_all_games(self) -> None:
        if not self.games:
            return

        win = ctk.CTkToplevel(self)
        win.title("Все установленные игры" if not self._use_full_library else "Вся библиотека")
        win.geometry("460x620")
        win.minsize(380, 420)
        win.transient(self)
        win.after(10, win.grab_set)

        count = len(self.games)
        word = plural_ru(count, "игра", "игры", "игр")
        if self._use_full_library:
            title = f"Вся библиотека: {count} {word}"
        else:
            title = f"Установлено {count} {word}"
        ctk.CTkLabel(win, text=title, font=("", 14, "bold")).pack(pady=(14, 6))

        scroll = ctk.CTkScrollableFrame(win)
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        installed_ids = {g.appid for g in self._installed_games}

        for game in sorted(self.games, key=lambda g: g.name.lower()):
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)

            label_text = game.name
            if self._use_full_library and game.appid not in installed_ids:
                label_text += "   ·  не установлена"

            ctk.CTkLabel(
                row,
                text=label_text,
                anchor="w",
                justify="left",
                wraplength=340,
            ).pack(side="left", fill="x", expand=True, padx=(6, 0))

            ctk.CTkButton(
                row,
                text="▶",
                width=32,
                height=26,
                command=lambda g=game: launch_game(g),
            ).pack(side="right", padx=(6, 4))

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
"""CustomTkinter GUI for steam-local-randomizer."""
from __future__ import annotations

import random
from collections.abc import Callable

import customtkinter as ctk

from .library_parser import Game, find_installed_games
from .launcher import launch_game
from .randomizer import filter_games, pick_random_game
from .steam_locator import SteamNotFoundError, find_steam_path
from . import __version__
from .i18n import plural_ru

# Задержки (мс) между кадрами анимации «рулетки».
# Начинаем быстро (эффект размытия), затем плавно замедляемся до полной остановки.
_SPIN_DELAYS: tuple[int, ...] = (
    40, 40, 45, 50, 55, 60, 70, 80, 90, 100,
    115, 130, 150, 175, 200, 230, 265, 300, 345, 400, 460, 530,
)


class SteamRandomizerApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(f"Steam Local Randomizer")
        self.geometry("540x420")
        self.minsize(460, 360)

        self.games: list[Game] = []
        self.current_game: Game | None = None
        self.rng = random.Random()

        self._rolling = False
        self._spin_after_id: str | None = None
        self._on_finish: Callable[[], None] | None = None

        self._build_ui()
        self._load_games()

    # ---- UI ----------------------------------------------------------

    def _build_ui(self) -> None:
        # Шапка: статус + кнопка «Все игры».
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(18, 4))

        self.status = ctk.CTkLabel(
            header, text="Ищем библиотеку Steam…", font=("", 13), anchor="w"
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

        # Крупный результат.
        self.result = ctk.CTkLabel(
            self,
            text="Нажмите «Крутить!»",
            font=("", 24, "bold"),
            wraplength=480,
            justify="center",
        )
        self.result.pack(pady=28, expand=True)

        # Большая кнопка рулетки.
        self.roll_btn = ctk.CTkButton(
            self,
            text="🎲  Крутить!",
            height=52,
            font=("", 17, "bold"),
            command=self._roll,
        )
        self.roll_btn.pack(fill="x", padx=22, pady=(0, 10))

        # Нижний ряд: Запустить / Крутить и запустить.
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=(0, 18))

        self.launch_btn = ctk.CTkButton(
            row, text="▶  Запустить", command=self._launch, state="disabled"
        )
        self.launch_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.roll_launch_btn = ctk.CTkButton(
            row, text="🎲▶  Крутить и запустить", command=self._roll_and_launch
        )
        self.roll_launch_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))
        version_label = ctk.CTkLabel(
            self,
            text=f"v{__version__}",
            font=("", 11),
            text_color=("gray50", "gray60"),
        )
        version_label.pack(side="bottom", anchor="e", padx=14, pady=(0, 6))

    # ---- Данные ------------------------------------------------------

    def _load_games(self) -> None:
        try:
            steam_path = find_steam_path()
        except SteamNotFoundError as exc:
            self._set_error(str(exc))
            return

        try:
            all_games = find_installed_games(steam_path)
        except Exception as exc:  # noqa: BLE001 — показываем пользователю
            self._set_error(f"Ошибка чтения библиотеки: {exc}")
            return

        self.games = filter_games(all_games)
        if not self.games:
            self._set_error("В библиотеке не найдено ни одной установленной игры.")
            return

        count = len(self.games)
        self.status.configure(
            text=f"{count} {plural_ru(count, 'игра', 'игры', 'игр')} в библиотеке"
        )
        self.show_all_btn.configure(state="normal")

    def _set_error(self, message: str) -> None:
        self.status.configure(text=message)
        self.roll_btn.configure(state="disabled")
        self.roll_launch_btn.configure(state="disabled")
        self.show_all_btn.configure(state="disabled")

    # ---- Действия ----------------------------------------------------

    def _roll(self, on_finish: Callable[[], None] | None = None) -> None:
        """Запустить анимацию рулетки. on_finish вызовется после остановки."""
        if self._rolling or not self.games:
            return

        self._rolling = True
        self._on_finish = on_finish
        self.current_game = None

        self.roll_btn.configure(state="disabled")
        self.roll_launch_btn.configure(state="disabled")
        self.launch_btn.configure(state="disabled")
        self.result.configure(text_color=("gray30", "gray60"))  # приглушаем во время прокрутки

        self._spin(step=0)

    def _spin(self, step: int) -> None:
        total = len(_SPIN_DELAYS)

        if step >= total:
            # Финал: делаем настоящий выбор.
            game = pick_random_game(self.games, self.rng)
            if game is not None:
                self.current_game = game
                self.result.configure(text=game.name, text_color=("gray10", "gray95"))
            self._finish_roll()
            return

        # Промежуточный кадр: показываем случайную игру из пула.
        self.result.configure(text=self.rng.choice(self.games).name)
        self._spin_after_id = self.after(
            _SPIN_DELAYS[step], lambda: self._spin(step + 1)
        )

    def _finish_roll(self) -> None:
        self._spin_after_id = None
        self._rolling = False

        self.roll_btn.configure(state="normal")
        self.roll_launch_btn.configure(state="normal")
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
        # Крутить, а когда остановится — запустить.
        self._roll(on_finish=self._launch)

    def _show_all_games(self) -> None:
        if not self.games:
            return

        win = ctk.CTkToplevel(self)
        win.title("Все установленные игры")
        win.geometry("440x600")
        win.minsize(360, 400)
        win.transient(self)
        win.after(10, win.grab_set)

        count = len(self.games)
        ctk.CTkLabel(
            win,
            text=f"Установлено {count} {plural_ru(count, 'игра', 'игры', 'игр')}",
            font=("", 14, "bold"),
        ).pack(pady=(14, 6))

        scroll = ctk.CTkScrollableFrame(win)
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        for game in sorted(self.games, key=lambda g: g.name.lower()):
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(
                row,
                text=game.name,
                anchor="w",
                justify="left",
                wraplength=320,
            ).pack(side="left", fill="x", expand=True, padx=(6, 0))

            ctk.CTkButton(
                row,
                text="▶",
                width=32,
                height=26,
                command=lambda g=game: launch_game(g),
            ).pack(side="right", padx=(6, 4))

    # ---- Очистка -----------------------------------------------------

    def destroy(self) -> None:
        # Отменяем отложенный кадр анимации, иначе Tk может ругнуться
        # на «invalid command name» при закрытии окна во время прокрутки.
        if self._spin_after_id is not None:
            try:
                self.after_cancel(self._spin_after_id)
            except Exception:
                pass
            self._spin_after_id = None
        super().destroy()


def main() -> int:
    app = SteamRandomizerApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
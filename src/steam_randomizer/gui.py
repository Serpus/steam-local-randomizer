"""CustomTkinter GUI for steam-local-randomizer."""
from __future__ import annotations

import random

import customtkinter as ctk

from .library_parser import Game, find_installed_games
from .launcher import launch_game
from .randomizer import filter_games, pick_random_game
from .steam_locator import SteamNotFoundError, find_steam_path


class SteamRandomizerApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Steam Local Randomizer")
        self.geometry("540x400")
        self.minsize(460, 340)

        self.games: list[Game] = []
        self.current_game: Game | None = None
        self.rng = random.Random()

        self._build_ui()
        self._load_games()

    # ---- UI ----------------------------------------------------------

    def _build_ui(self) -> None:
        self.status = ctk.CTkLabel(self, text="Ищем библиотеку Steam…", font=("", 13))
        self.status.pack(pady=(18, 4))

        self.result = ctk.CTkLabel(
            self,
            text="—",
            font=("", 26, "bold"),
            wraplength=480,
            justify="center",
        )
        self.result.pack(pady=28, expand=True)

        self.roll_btn = ctk.CTkButton(
            self,
            text="🎲  Roll!",
            height=52,
            font=("", 17, "bold"),
            command=self._roll,
        )
        self.roll_btn.pack(fill="x", padx=22, pady=(0, 10))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=(0, 18))

        self.launch_btn = ctk.CTkButton(
            row,
            text="▶  Launch",
            command=self._launch,
            state="disabled",
        )
        self.launch_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.roll_launch_btn = ctk.CTkButton(
            row,
            text="🎲▶  Roll & Launch",
            command=self._roll_and_launch,
        )
        self.roll_launch_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))

    # ---- Data --------------------------------------------------------

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

        self.status.configure(text=f"{len(self.games)} игр в библиотеке · {steam_path}")

    def _set_error(self, message: str) -> None:
        self.status.configure(text=message)
        self.roll_btn.configure(state="disabled")
        self.roll_launch_btn.configure(state="disabled")

    # ---- Actions -----------------------------------------------------

    def _roll(self) -> None:
        game = pick_random_game(self.games, self.rng)
        if game is None:
            return
        self.current_game = game
        self.result.configure(text=game.name)
        self.launch_btn.configure(state="normal")

    def _launch(self) -> None:
        if self.current_game is not None:
            launch_game(self.current_game)

    def _roll_and_launch(self) -> None:
        self._roll()
        self._launch()


def main() -> int:
    app = SteamRandomizerApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
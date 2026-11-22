"""Индикатор загрузки: анимированные точки в статусе + прогресс-бар."""
from __future__ import annotations


class LoadingIndicator:
    def __init__(self, master, status, progress, *, before) -> None:
        self._master = master
        self._status = status
        self._progress = progress
        self._before = before
        self.active = False
        self._after_id: str | None = None
        self._base = ""

    def start(self, message: str) -> None:
        self.active = True
        self._base = message
        try:
            self._progress.pack(fill="x", padx=22, pady=(6, 0), before=self._before)
            self._progress.start()
        except Exception:
            pass
        self._tick(0)

    def _tick(self, dots: int) -> None:
        if not self.active:
            return
        self._status.configure(text=self._base + "." * (dots % 4))
        self._after_id = self._master.after(350, lambda: self._tick(dots + 1))

    def stop(self) -> None:
        self.active = False
        if self._after_id is not None:
            try:
                self._master.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        try:
            self._progress.stop()
            self._progress.pack_forget()
        except Exception:
            pass
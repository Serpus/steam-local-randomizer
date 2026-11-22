#!/usr/bin/env python3
"""GUI release helper: two-stage process.

Stage 1 (Подготовить) — bump version in __init__.py and README.md,
                       git add, commit, tag (locally).
Stage 2 (Опубликовать) — git push branch + git push origin tag.

Double-click release.bat — or run `python release_gui.py`.
"""
from __future__ import annotations

import re
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

ROOT = Path(__file__).resolve().parent
INIT_FILE = ROOT / "src" / "steam_randomizer" / "__init__.py"
README_FILE = ROOT / "README.md"

VERSION_DEF_RE = re.compile(r'__version__\s*=\s*["\']([^"\']+)["\']')
VERSION_REPLACE_RE = re.compile(r'(__version__\s*=\s*["\'])([^"\']+)(["\'])')
BADGE_RE = re.compile(r'(shields\.io/badge/version-)\d+\.\d+\.\d+(-blue)')
SEMVER_RE = re.compile(r'^(\d+)\.(\d+)\.(\d+)$')


# ----------------------------------------------------------------------------- helpers

def read_current_version() -> str:
    m = VERSION_DEF_RE.search(INIT_FILE.read_text(encoding="utf-8"))
    if not m:
        raise RuntimeError(f"__version__ not found in {INIT_FILE}")
    return m.group(1)


def parse_semver(s: str) -> tuple[int, int, int]:
    m = SEMVER_RE.fullmatch(s)
    if not m:
        raise ValueError(f"Invalid version {s!r} — expected MAJOR.MINOR.PATCH")
    return tuple(int(x) for x in m.groups())  # type: ignore[return-value]


def compute_next(current: str, bump: str) -> str:
    major, minor, patch = parse_semver(current)
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "major":
        return f"{major + 1}.0.0"
    raise ValueError(bump)


def update_init(new_version: str) -> None:
    text = INIT_FILE.read_text(encoding="utf-8")
    new_text, n = VERSION_REPLACE_RE.subn(
        lambda m: f"{m.group(1)}{new_version}{m.group(3)}", text, count=1
    )
    if n != 1:
        raise RuntimeError(f"failed to update __version__ in {INIT_FILE}")
    INIT_FILE.write_text(new_text, encoding="utf-8")


def update_readme(new_version: str) -> bool:
    if not README_FILE.is_file():
        return False
    text = README_FILE.read_text(encoding="utf-8")
    new_text, n = BADGE_RE.subn(rf"\g<1>{new_version}\g<2>", text, count=1)
    if n == 0:
        return False
    README_FILE.write_text(new_text, encoding="utf-8")
    return True


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, check=check, capture_output=True, text=True)


def tag_exists(tag: str) -> bool:
    return bool(run(["git", "tag", "--list", tag], check=False).stdout.strip())


def git_branch() -> str:
    return run(["git", "branch", "--show-current"], check=False).stdout.strip()


def git_last_commit() -> str:
    return run(["git", "log", "-1", "--oneline"], check=False).stdout.strip()


def git_head_hash() -> str:
    return run(["git", "rev-parse", "HEAD"], check=False).stdout.strip()


def git_is_dirty() -> list[str]:
    out = run(["git", "status", "--porcelain"], check=False).stdout
    return [line for line in out.splitlines() if line.strip()]


def repo_slug() -> str | None:
    try:
        result = run(["git", "remote", "get-url", "origin"], check=False)
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", result.stdout.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


# ----------------------------------------------------------------------------- UI

class ReleaseDialog(tk.Tk):
    """Two-stage release: prepare locally, then publish to GitHub."""

    FONT_BASE = ("Segoe UI", 10)
    FONT_BOLD = ("Segoe UI", 10, "bold")
    FONT_BIG = ("Segoe UI", 14, "bold")
    FONT_MONO = ("Consolas", 12)

    def __init__(self) -> None:
        super().__init__()
        self.title("Release Steam Local Randomizer")
        self.geometry("560x520")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.stage = "idle"          # idle | prepared | published
        self.tag: str | None = None
        self.new_version: str | None = None
        self.orig_hash: str | None = None
        self.quick_btns: list[tk.Button] = []

        try:
            self.current = read_current_version()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Error", str(e))
            self.destroy()
            return

        self._build_ui()
        self._set_version(compute_next(self.current, "patch"))

    # ---- UI ----------------------------------------------------------

    def _build_ui(self) -> None:
        tk.Label(self, text="🚀 Release Steam Local Randomizer",
                 font=self.FONT_BIG).pack(pady=(16, 4))

        branch = git_branch()
        commit = git_last_commit()
        git_label = f"Branch: {branch}   ·   {commit}" if commit else "git info unavailable"
        git_color = "#2c7a2c" if branch == "main" else "#c0392b"
        tk.Label(self, text=git_label, font=("Segoe UI", 9), fg=git_color).pack()

        if branch and branch != "main":
            tk.Label(self, text="⚠ Not on main branch — release from main!",
                     font=("Segoe UI", 9, "bold"), fg="#c0392b").pack(pady=(2, 0))

        tk.Frame(self, height=1, bg="#ddd").pack(fill="x", padx=16, pady=10)

        # Current version
        tk.Label(self, text="Current version", font=self.FONT_BASE,
                 fg="#666").pack()
        tk.Label(self, text=self.current,
                 font=("Consolas", 18, "bold")).pack(pady=(0, 10))

        # Quick-bump row
        quick = tk.Frame(self)
        quick.pack(pady=4)
        for label, bump in (("Patch", "patch"), ("Minor", "minor"), ("Major", "major")):
            btn = tk.Button(
                quick, text=label, width=10,
                command=lambda b=bump: self._set_version(compute_next(self.current, b)),
            )
            btn.pack(side="left", padx=4)
            self.quick_btns.append(btn)

        # Version entry
        entry_row = tk.Frame(self)
        entry_row.pack(pady=14)
        tk.Label(entry_row, text="New version:", font=self.FONT_BASE
                 ).pack(side="left", padx=(0, 8))
        self.version_var = tk.StringVar()
        self.version_var.trace_add("write", lambda *_: self._update_preview())
        self.entry = tk.Entry(entry_row, textvariable=self.version_var,
                              font=self.FONT_MONO, width=16, justify="center")
        self.entry.pack(side="left")

        # Preview / validation
        self.preview = tk.Label(self, text="", font=self.FONT_BASE)
        self.preview.pack(pady=2)

        tk.Frame(self, height=1, bg="#ddd").pack(fill="x", padx=16, pady=10)

        # Status panel
        self.status = tk.Label(self, text="", font=("Segoe UI", 9),
                               fg="#444", wraplength=520, justify="center")
        self.status.pack(pady=(0, 10))

        # Buttons container (покажем нужные по стадии)
        self.button_bar = tk.Frame(self)
        self.button_bar.pack(pady=(4, 16))
        self._render_buttons()

    def _render_buttons(self) -> None:
        for w in self.button_bar.winfo_children():
            w.destroy()

        if self.stage == "idle":
            tk.Button(self.button_bar, text="Закрыть", width=12,
                      command=self._on_close).pack(side="left", padx=4)
            self.prepare_btn = tk.Button(
                self.button_bar, text="📦  Подготовить релиз", width=22,
                bg="#2c7a2c", fg="white",
                activebackground="#235f23", activeforeground="white",
                font=self.FONT_BOLD, command=self._on_prepare,
            )
            self.prepare_btn.pack(side="left", padx=4)

        elif self.stage == "prepared":
            tk.Button(self.button_bar, text="↶  Отменить", width=14,
                      command=self._on_revert).pack(side="left", padx=4)
            self.publish_btn = tk.Button(
                self.button_bar, text="🚀  Опубликовать релиз", width=22,
                bg="#1f6feb", fg="white",
                activebackground="#1958c0", activeforeground="white",
                font=self.FONT_BOLD, command=self._on_publish,
            )
            self.publish_btn.pack(side="left", padx=4)

    # ---- callbacks ---------------------------------------------------

    def _set_version(self, v: str) -> None:
        if self.stage != "idle":
            return
        self.version_var.set(v)
        self.entry.focus_set()
        self.entry.select_range(0, "end")
        self.entry.icursor("end")

    def _update_preview(self) -> None:
        if self.stage != "idle":
            return
        v = self.version_var.get().strip()
        try:
            new = parse_semver(v)
            cur = parse_semver(self.current)
            if new <= cur:
                self.preview.config(text="⚠ Новая версия должна быть больше текущей",
                                    fg="#c0392b")
                self.prepare_btn.config(state="disabled")
                return
            tag = f"v{v}"
            if tag_exists(tag):
                self.preview.config(text=f"⚠ Тег {tag} уже существует",
                                    fg="#c0392b")
                self.prepare_btn.config(state="disabled")
                return
            self.preview.config(text=f"Будет создан тег {tag}", fg="#2c7a2c")
            self.prepare_btn.config(state="normal")
        except ValueError as e:
            self.preview.config(text=str(e), fg="#c0392b")
            self.prepare_btn.config(state="disabled")

    def _set_status(self, msg: str) -> None:
        self.status.config(text=msg)
        self.update_idletasks()

    def _on_prepare(self) -> None:
        new_version = self.version_var.get().strip()
        tag = f"v{new_version}"

        # Require a clean working tree before we start — this makes revert safe.
        dirty = git_is_dirty()
        if dirty:
            preview = "\n".join(f"  • {line}" for line in dirty[:10])
            more = f"\n  … и ещё {len(dirty) - 10}" if len(dirty) > 10 else ""
            messagebox.showerror(
                "Рабочая папка не чистая",
                f"Перед подготовкой релиза закоммитьте или откатите изменения:\n\n"
                f"{preview}{more}\n\n"
                f"Затем запустите снова."
            )
            return

        if not messagebox.askyesno(
            "Подготовить релиз",
            f"Подготовить {tag} локально?\n\n"
            f"Что будет сделано:\n"
            f"  • обновится версия в src/steam_randomizer/__init__.py\n"
            f"  • обновится бейдж в README.md\n"
            f"  • git add -A\n"
            f"  • git commit -m \"chore: release {tag}\"\n"
            f"  • git tag {tag}\n\n"
            f"Публикация НЕ произойдёт — её запустите отдельно."
        ):
            return

        self.prepare_btn.config(state="disabled", text="Подготовка…")

        self.orig_hash = git_head_hash()
        try:
            self._set_status("Обновляем файлы…")
            update_init(new_version)
            update_readme(new_version)

            self._set_status("git add -A…")
            run(["git", "add", "-A"])

            self._set_status("git commit…")
            run(["git", "commit", "-m", f"chore: release {tag}"])

            self._set_status(f"git tag {tag}…")
            run(["git", "tag", tag])
        except Exception as e:  # noqa: BLE001
            self._rollback_prepare(tag)
            messagebox.showerror("Ошибка при подготовке",
                                 f"{e}\n\nИзменения откачены.")
            self.prepare_btn.config(state="normal", text="📦  Подготовить релиз")
            self._set_status("")
            return

        # success
        self.stage = "prepared"
        self.tag = tag
        self.new_version = new_version

        commit = git_last_commit()
        self._set_status(
            f"✓ Подготовлен релиз {tag}\n"
            f"Коммит: {commit}\n"
            f"Готов к публикации — нажмите «Опубликовать релиз»."
        )
        self.entry.config(state="disabled")
        for b in self.quick_btns:
            b.config(state="disabled")
        self.preview.config(text="", fg="#444")
        self._render_buttons()

    def _rollback_prepare(self, tag: str) -> None:
        """Best-effort rollback of a partially-prepared release."""
        if self.orig_hash:
            run(["git", "reset", "--hard", self.orig_hash], check=False)
        run(["git", "tag", "-d", tag], check=False)

    def _on_revert(self) -> None:
        if self.stage != "prepared" or not self.tag:
            return
        if not messagebox.askyesno(
            "Отменить подготовку",
            f"Удалить локальный коммит и тег {self.tag}?\n\n"
            f"Файлы вернутся к состоянию до подготовки."
        ):
            return

        try:
            if self.orig_hash:
                run(["git", "reset", "--hard", self.orig_hash])
            run(["git", "tag", "-d", self.tag])
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Не удалось отменить", str(e))
            return

        self.stage = "idle"
        self.tag = None
        self.new_version = None
        self.orig_hash = None
        self.entry.config(state="normal")
        for b in self.quick_btns:
            b.config(state="normal")
        self._set_status("")
        self._update_preview()
        self._render_buttons()

    def _on_publish(self) -> None:
        if self.stage != "prepared" or not self.tag:
            return

        tag = self.tag
        self.publish_btn.config(state="disabled", text="Публикация…")

        self._set_status("git push (branch)…")
        try:
            run(["git", "push"])
        except subprocess.CalledProcessError as e:
            self._set_status("")
            messagebox.showerror(
                "Ошибка публикации",
                f"Не удалось запушить ветку:\n{e.stderr or e.stdout}\n\n"
                f"Коммит и тег {tag} остаются локально. Повторите попытку."
            )
            self.publish_btn.config(state="normal", text="🚀  Опубликовать релиз")
            return

        self._set_status(f"git push origin {tag}…")
        try:
            run(["git", "push", "origin", tag])
        except subprocess.CalledProcessError as e:
            self._set_status("")
            messagebox.showerror(
                "Ветка запушена, тег — нет",
                f"Ветка ушла, но тег {tag} — нет:\n{e.stderr or e.stdout}\n\n"
                f"Отправьте вручную: git push origin {tag}"
            )
            self.publish_btn.config(state="normal", text="🚀  Опубликовать релиз")
            return

        self.stage = "published"
        slug = repo_slug()
        msg = (f"✓ Релиз {tag} опубликован!\n\n"
               f"GitHub Actions соберёт .exe за 3–5 минут.")
        if slug:
            msg += (f"\n\nActions:  https://github.com/{slug}/actions"
                    f"\nReleases: https://github.com/{slug}/releases")
        messagebox.showinfo("Готово", msg)
        self.destroy()

    def _on_close(self) -> None:
        if self.stage == "prepared" and self.tag:
            if not messagebox.askyesno(
                "Релиз не опубликован",
                f"Релиз {self.tag} подготовлен локально (коммит + тег), "
                f"но НЕ опубликован.\n\n"
                f"Закрыть окно? Коммит и тег останутся локально. "
                f"Опубликовать можно командой:\n\n"
                f"  git push && git push origin {self.tag}"
            ):
                return
        self.destroy()


def main() -> int:
    try:
        app = ReleaseDialog()
        app.mainloop()
    except Exception as e:  # noqa: BLE001
        import traceback
        try:
            messagebox.showerror("Критическая ошибка",
                                 f"{e}\n\n{traceback.format_exc()}")
        except Exception:
            print(traceback.format_exc())
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
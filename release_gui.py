#!/usr/bin/env python3
"""GUI release helper: two-stage process, git operations only on publish.

Stage 1 (Подготовить) — bump version in __init__.py and README.md only.
                        Original file contents are kept in memory for rollback.
Stage 2 (Опубликовать) — git add, commit, tag, push, push tag.

Git operations run in a background thread so the UI stays responsive
during slow pushes. A progress bar and live status keep the user informed.

Double-click release.bat — or run `python release_gui.py`.
"""
from __future__ import annotations

import re
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

ROOT = Path(__file__).resolve().parent
INIT_FILE = ROOT / "src" / "steam_randomizer" / "__init__.py"
README_FILE = ROOT / "README.md"

VERSION_DEF_RE = re.compile(r'__version__\s*=\s*["\']([^"\']+)["\']')
VERSION_REPLACE_RE = re.compile(r'(__version__\s*=\s*["\'])([^"\']+)(["\'])')
BADGE_RE = re.compile(r'(shields\.io/badge/version-)\d+\.\d+\.\d+(-blue)')
SEMVER_RE = re.compile(r'^(\d+)\.(\d+)\.(\d+)$')


# ----------------------------------------------------------------------------- helpers

def _recover_tuple_string(s: str) -> str | None:
    """Recover '(1, 0, 4)' -> '1.0.4'. Returns None if not applicable."""
    s = s.strip()
    if not (s.startswith("(") and s.endswith(")")):
        return None
    inner = s[1:-1]
    parts = [p.strip() for p in inner.split(",")]
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        return ".".join(parts)
    return None


def read_current_version() -> str:
    text = INIT_FILE.read_text(encoding="utf-8")
    m = VERSION_DEF_RE.search(text)
    if not m:
        raise RuntimeError(f"__version__ not found in {INIT_FILE}")
    raw = m.group(1)

    recovered = _recover_tuple_string(raw)
    if recovered is not None:
        # Auto-fix the file so this doesn't keep happening.
        new_text = VERSION_REPLACE_RE.subn(
            lambda mm: f"{mm.group(1)}{recovered}{mm.group(3)}",
            text, count=1,
        )[0]
        INIT_FILE.write_text(new_text, encoding="utf-8")
        return recovered

    return raw


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


def _apply_version_to_init(text: str, new_version: str) -> str:
    if not isinstance(new_version, str) or not SEMVER_RE.fullmatch(new_version):
        raise ValueError(f"invalid new_version: {new_version!r}")
    new_text, n = VERSION_REPLACE_RE.subn(
        lambda m: f"{m.group(1)}{new_version}{m.group(3)}", text, count=1
    )
    if n != 1:
        raise RuntimeError("failed to update __version__")
    return new_text


def _apply_version_to_readme(text: str, new_version: str) -> tuple[str, bool]:
    if not isinstance(new_version, str) or not SEMVER_RE.fullmatch(new_version):
        raise ValueError(f"invalid new_version: {new_version!r}")
    # Normal case
    new_text, n = BADGE_RE.subn(rf"\g<1>{new_version}\g<2>", text, count=1)
    BADGE_CORRUPT_RE = re.compile(
        r'(shields\.io/badge/version-)\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)(-blue)'
    )
    if n > 0:
        return new_text, True
    # Recovery from corrupt badge like  version-(1, 0, 4)-blue
    new_text, n = BADGE_CORRUPT_RE.subn(rf"\g<1>{new_version}\g<2>", text, count=1)
    return new_text, n > 0


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a subprocess, forcing UTF-8 decoding regardless of Windows locale."""
    return subprocess.run(
        cmd,
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def git_branch() -> str:
    return run(["git", "branch", "--show-current"], check=False).stdout.strip()


def git_default_branch() -> str | None:
    r = run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"], check=False)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().rsplit("/", 1)[-1]
    return None


def git_last_commit(max_len: int = 60) -> str:
    r = run(["git", "log", "-1", "--oneline"], check=False)
    line = r.stdout.strip()
    if len(line) > max_len:
        line = line[: max_len - 1] + "…"
    return line


def git_all_tags() -> set[str]:
    r = run(["git", "tag", "--list"], check=False)
    return {line.strip() for line in r.stdout.splitlines() if line.strip()}


def git_is_dirty() -> list[str]:
    out = run(["git", "status", "--porcelain"], check=False).stdout
    return [line for line in out.splitlines() if line.strip()]


def git_diff_stat() -> str:
    return run(["git", "diff", "--stat"], check=False).stdout.strip()


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
    """Two-stage release: edit files locally, then run git operations on publish."""

    FONT_BASE = ("Segoe UI", 10)
    FONT_BOLD = ("Segoe UI", 10, "bold")
    FONT_BIG = ("Segoe UI", 14, "bold")
    FONT_MONO = ("Consolas", 12)

    def __init__(self) -> None:
        super().__init__()
        self.title("Release Steam Local Randomizer")
        self.geometry("580x560")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.stage = "idle"          # idle | prepared | published
        self.tag: str | None = None
        self.new_version: str | None = None
        self.orig_init_content: str | None = None
        self.orig_readme_content: str | None = None
        self.orig_readme_existed: bool = False
        self.quick_btns: list[tk.Button] = []
        self._working = False

        try:
            self.current = read_current_version()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Error", str(e))
            self.destroy()
            return

        self._git = self._collect_git_state()

        self._build_ui()
        self._set_version(compute_next(self.current, "patch"))

    def _collect_git_state(self) -> dict:
        return {
            "branch": git_branch(),
            "default_branch": git_default_branch(),
            "last_commit": git_last_commit(),
            "tags": git_all_tags(),
        }

    def _refresh_git_state(self) -> None:
        self._git = self._collect_git_state()

    # ---- UI ----------------------------------------------------------

    def _build_ui(self) -> None:
        tk.Label(self, text="🚀 Release Steam Local Randomizer",
                 font=self.FONT_BIG).pack(pady=(16, 4))

        branch = self._git["branch"]
        default = self._git["default_branch"]
        commit = self._git["last_commit"]
        on_default = (default is None) or (branch == default)

        git_label = f"Branch: {branch}"
        if default and branch != default:
            git_label += f"   (default: {default})"
        if commit:
            git_label += f"   ·   {commit}"
        tk.Label(self, text=git_label, font=("Segoe UI", 9),
                 fg="#2c7a2c" if on_default else "#c0392b").pack()

        if not on_default:
            tk.Label(self,
                     text=f"⚠ Not on default branch '{default}' — release from it!",
                     font=("Segoe UI", 9, "bold"), fg="#c0392b").pack(pady=(2, 0))

        tk.Frame(self, height=1, bg="#ddd").pack(fill="x", padx=16, pady=10)

        tk.Label(self, text="Current version", font=self.FONT_BASE,
                 fg="#666").pack()
        tk.Label(self, text=self.current,
                 font=("Consolas", 18, "bold")).pack(pady=(0, 10))

        quick = tk.Frame(self)
        quick.pack(pady=4)
        for label, bump in (("Patch", "patch"), ("Minor", "minor"), ("Major", "major")):
            btn = tk.Button(
                quick, text=label, width=10,
                command=lambda b=bump: self._set_version(compute_next(self.current, b)),
            )
            btn.pack(side="left", padx=4)
            self.quick_btns.append(btn)

        entry_row = tk.Frame(self)
        entry_row.pack(pady=14)
        tk.Label(entry_row, text="New version:", font=self.FONT_BASE
                 ).pack(side="left", padx=(0, 8))
        self.version_var = tk.StringVar()
        self.version_var.trace_add("write", lambda *_: self._update_preview())
        self.entry = tk.Entry(entry_row, textvariable=self.version_var,
                              font=self.FONT_MONO, width=16, justify="center")
        self.entry.pack(side="left")

        self.preview = tk.Label(self, text="", font=self.FONT_BASE)
        self.preview.pack(pady=2)

        tk.Frame(self, height=1, bg="#ddd").pack(fill="x", padx=16, pady=10)

        # Status label — показывает шаг операции.
        self.status = tk.Label(self, text="", font=("Segoe UI", 9),
                               fg="#444", wraplength=540, justify="center")
        self.status.pack(pady=(0, 6))

        # Прогресс-бар — виден только во время работы (packed on demand).
        self.progress = ttk.Progressbar(self, mode="indeterminate", length=520)

        # Кнопки.
        self.button_bar = tk.Frame(self)
        self.button_bar.pack(pady=(6, 16))
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

    # ---- progress helpers --------------------------------------------

    def _start_progress(self, msg: str) -> None:
        self._working = True
        self.status.config(text=msg)
        self.progress.pack(fill="x", padx=16, pady=(0, 8),
                           before=self.button_bar)
        self.progress.start(12)

    def _update_progress_status(self, msg: str) -> None:
        self.status.config(text=msg)

    def _hide_progress(self) -> None:
        self._working = False
        try:
            self.progress.stop()
        except Exception:
            pass
        try:
            self.progress.pack_forget()
        except Exception:
            pass

    def _safe_after(self, func, *args) -> None:
        """Schedule a call in the main thread, safe to call from a thread."""
        def wrapper() -> None:
            try:
                func(*args)
            except Exception:
                pass
        try:
            self.after(0, wrapper)
        except Exception:
            pass

    # ---- callbacks ---------------------------------------------------

    def _set_version(self, v: str) -> None:
        if self.stage != "idle" or self._working:
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
            if tag in self._git["tags"]:
                self.preview.config(text=f"⚠ Тег {tag} уже существует",
                                    fg="#c0392b")
                self.prepare_btn.config(state="disabled")
                return
            self.preview.config(text=f"Релиз будет помечен как {tag}", fg="#2c7a2c")
            self.prepare_btn.config(state="normal")
        except ValueError as e:
            self.preview.config(text=str(e), fg="#c0392b")
            self.prepare_btn.config(state="disabled")

    def _set_status(self, msg: str) -> None:
        self.status.config(text=msg)
        self.update_idletasks()

    # ---- stage 1: prepare --------------------------------------------

    def _on_prepare(self) -> None:
        if self._working or self.stage != "idle":
            return

        v = self.version_var.get().strip()
        try:
            new = parse_semver(v)
            cur = parse_semver(self.current)
        except ValueError as e:
            messagebox.showerror("Ошибка", str(e))
            return

        if new <= cur:
            messagebox.showerror("Ошибка",
                                 "Новая версия должна быть больше текущей.")
            return

        tag = f"v{v}"
        if tag in self._git["tags"]:
            messagebox.showerror("Ошибка", f"Тег {tag} уже существует.")
            return

        if not messagebox.askyesno(
            "Подготовить релиз",
            f"Подготовить изменения для {tag}?\n\n"
            f"Будет сделано:\n"
            f"  • обновится версия в src/steam_randomizer/__init__.py\n"
            f"  • обновится бейдж в README.md\n\n"
            f"Git-операции (commit, tag, push) НЕ выполняются.\n"
            f"Их можно запустить кнопкой «Опубликовать релиз»."
        ):
            return

        # Snapshot originals in main thread (file reads, fast).
        try:
            self.orig_init_content = INIT_FILE.read_text(encoding="utf-8")
            if README_FILE.is_file():
                self.orig_readme_content = README_FILE.read_text(encoding="utf-8")
                self.orig_readme_existed = True
            else:
                self.orig_readme_content = None
                self.orig_readme_existed = False
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Ошибка чтения файлов", str(e))
            return

        self.prepare_btn.config(state="disabled", text="Подготовка…")
        self._start_progress("Проверяем git-состояние…")

        threading.Thread(
            target=self._prepare_bg,
            args=(v, tag),
            daemon=True,
        ).start()

    def _prepare_bg(self, new_version: str, tag: str) -> None:
        try:
            self._safe_after(self._update_progress_status, "Проверяем теги…")
            if tag in git_all_tags():
                raise RuntimeError(f"Тег {tag} уже существует.")

            self._safe_after(self._update_progress_status, "Проверяем рабочую папку…")
            dirty = git_is_dirty()
            if dirty:
                preview = "\n".join(f"  • {line}" for line in dirty[:5])
                more = f"\n  … и ещё {len(dirty) - 5}" if len(dirty) > 5 else ""
                raise RuntimeError(
                    f"Рабочая папка не чистая:\n{preview}{more}\n\n"
                    f"Закоммитьте или откатите изменения и попробуйте снова."
                )

            self._safe_after(self._update_progress_status, "Обновляем файлы…")
            new_init = _apply_version_to_init(self.orig_init_content, new_version)
            INIT_FILE.write_text(new_init, encoding="utf-8")

            if self.orig_readme_existed and self.orig_readme_content is not None:
                new_readme, _ = _apply_version_to_readme(
                    self.orig_readme_content, new_version
                )
                README_FILE.write_text(new_readme, encoding="utf-8")

            self._safe_after(self._update_progress_status, "Получаем diff…")
            diff = git_diff_stat()

            self._safe_after(self._on_prepare_success, new_version, tag, diff)
        except Exception as e:  # noqa: BLE001
            try:
                self._restore_files()
            except Exception:
                pass
            self._safe_after(self._on_prepare_error, str(e))

    def _on_prepare_success(self, new_version: str, tag: str, diff: str) -> None:
        self._hide_progress()
        self.stage = "prepared"
        self.tag = tag
        self.new_version = new_version

        self._set_status(
            f"✓ Файлы обновлены — {tag}\n\n"
            f"{diff}\n\n"
            f"Изменения НЕ закоммичены.\n"
            f"Проверьте их в редакторе — и нажмите «Опубликовать релиз».\n"
            f"«Отменить» вернёт файлы к исходному виду."
        )
        self.entry.config(state="disabled")
        for b in self.quick_btns:
            b.config(state="disabled")
        self.preview.config(text="", fg="#444")
        self._render_buttons()

    def _on_prepare_error(self, msg: str) -> None:
        self._hide_progress()
        self.stage = "idle"
        self.tag = None
        self.new_version = None
        self.orig_init_content = None
        self.orig_readme_content = None
        self.orig_readme_existed = False
        self.prepare_btn.config(state="normal", text="📦  Подготовить релиз")
        self._set_status("")
        self._update_preview()
        messagebox.showerror("Ошибка при подготовке", msg)

    def _restore_files(self) -> None:
        if self.orig_init_content is not None:
            INIT_FILE.write_text(self.orig_init_content, encoding="utf-8")
        if self.orig_readme_existed and self.orig_readme_content is not None:
            README_FILE.write_text(self.orig_readme_content, encoding="utf-8")

    def _on_revert(self) -> None:
        if self._working or self.stage != "prepared":
            return
        if not messagebox.askyesno(
            "Отменить подготовку",
            f"Вернуть файлы к состоянию до подготовки {self.tag}?\n\n"
            f"Git-операции не выполнялись, так что достаточно восстановить файлы."
        ):
            return

        self._restore_files()
        self.stage = "idle"
        self.tag = None
        self.new_version = None
        self.orig_init_content = None
        self.orig_readme_content = None
        self.orig_readme_existed = False
        self.entry.config(state="normal")
        for b in self.quick_btns:
            b.config(state="normal")
        self._set_status("")
        self._update_preview()
        self._render_buttons()

    # ---- stage 2: publish --------------------------------------------

    def _on_publish(self) -> None:
        if self._working or self.stage != "prepared" or not self.tag:
            return

        tag = self.tag

        if not messagebox.askyesno(
            "Опубликовать релиз",
            f"Запустить git-операции для {tag}?\n\n"
            f"  • git add -A\n"
            f"  • git commit -m \"chore: release {tag}\"\n"
            f"  • git tag {tag}\n"
            f"  • git push\n"
            f"  • git push origin {tag}\n\n"
            f"После пуша GitHub Actions соберёт .exe (~3–5 минут)."
        ):
            return

        self.publish_btn.config(state="disabled", text="Публикация…")
        self._start_progress("git add -A…")

        threading.Thread(
            target=self._publish_bg,
            args=(tag,),
            daemon=True,
        ).start()

    def _publish_bg(self, tag: str) -> None:
        try:
            self._safe_after(self._update_progress_status, "git add -A…")
            run(["git", "add", "-A"])

            self._safe_after(self._update_progress_status, "git commit…")
            run(["git", "commit", "-m", f"chore: release {tag}"])

            self._safe_after(self._update_progress_status, f"git tag {tag}…")
            run(["git", "tag", tag])

            self._safe_after(self._update_progress_status, "git push (branch)…")
            run(["git", "push"])

            self._safe_after(self._update_progress_status,
                             f"git push origin {tag}…")
            run(["git", "push", "origin", tag])

            self._safe_after(self._on_publish_success, tag)
        except subprocess.CalledProcessError as e:
            err = (e.stderr or e.stdout or str(e)).strip()
            self._safe_after(self._on_publish_error, tag, err)
        except Exception as e:  # noqa: BLE001
            self._safe_after(self._on_publish_error, tag, str(e))

    def _on_publish_success(self, tag: str) -> None:
        self._hide_progress()
        self.stage = "published"
        slug = repo_slug()
        msg = (f"✓ Релиз {tag} опубликован!\n\n"
               f"GitHub Actions соберёт .exe за 3–5 минут.")
        if slug:
            msg += (f"\n\nActions:  https://github.com/{slug}/actions"
                    f"\nReleases: https://github.com/{slug}/releases")
        messagebox.showinfo("Готово", msg)
        self.destroy()

    def _on_publish_error(self, tag: str, err: str) -> None:
        self._hide_progress()
        self.publish_btn.config(state="normal", text="🚀  Опубликовать релиз")
        messagebox.showerror(
            "Ошибка публикации",
            f"Git-команда провалилась:\n\n{err}\n\n"
            f"Что уже сделано локально:\n"
            f"  • файлы обновлены\n"
            f"  • возможно, есть локальный коммит и тег {tag}\n\n"
            f"Проверьте `git log` и `git tag`, при необходимости:\n"
            f"  git reset --hard HEAD~1\n"
            f"  git tag -d {tag}"
        )

    def _on_close(self) -> None:
        if self._working:
            messagebox.showwarning(
                "Подождите",
                "Операция ещё выполняется.\n"
                "Дождитесь её завершения и попробуйте снова."
            )
            return
        if self.stage == "prepared" and self.tag:
            answer = messagebox.askyesno(
                "Релиз не опубликован",
                f"Файлы подготовлены для {self.tag}, но НЕ закоммичены.\n\n"
                f"Восстановить исходное содержимое файлов?\n\n"
                f"Да — вернуть как было (безопасно)\n"
                f"Нет — оставить файлы изменёнными, чтобы вы могли проверить вручную\n\n"
                f"Внимание: git-операции не выполнялись."
            )
            if answer:
                self._restore_files()
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
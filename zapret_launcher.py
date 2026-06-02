# -*- coding: utf-8 -*-
"""
Discord/YouTube Ускоритель — простой лаунчер для zapret-discord-youtube (Flowseal).

Что делает по одной кнопке:
  1. Скачивает последний релиз с GitHub (если ещё не скачан или вышла новая версия).
  2. Распаковывает в ASCII-путь (C:\\ProgramData\\ZapretLauncher), чтобы не мешала кириллица.
  3. Находит самую новую ALT-стратегию (general (ALT12).bat и т.п.) и запускает её.
  4. Повторное нажатие — выключает обход (закрывает winws.exe).

Программе нужны права администратора (драйвер WinDivert). Она запрашивает их сама.
"""

from __future__ import annotations

import os
import time
import re
import sys
import json
import ctypes
import zipfile
import threading
import subprocess
import urllib.request
import urllib.error

import tkinter as tk
from tkinter import ttk, messagebox

# ----------------------------------------------------------------------------- #
#  Константы
# ----------------------------------------------------------------------------- #
REPO          = "Flowseal/zapret-discord-youtube"
API_LATEST    = f"https://api.github.com/repos/{REPO}/releases/latest"
INSTALL_DIR   = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                             "ZapretLauncher")
FILES_DIR     = os.path.join(INSTALL_DIR, "files")        # сюда распаковываем релиз
VERSION_FILE  = os.path.join(INSTALL_DIR, "version.txt")  # кэш установленной версии
APP_TITLE     = "Discord / YouTube Ускоритель"
USER_AGENT    = "ZapretLauncher/1.0 (+https://github.com/Flowseal/zapret-discord-youtube)"

CREATE_NO_WINDOW = 0x08000000  # флаг, чтобы не мигали чёрные консольные окна

# Цвета интерфейса
BG       = "#1e1f2b"
CARD     = "#262838"
TEXT     = "#e6e6f0"
MUTED    = "#8b8da3"
GREEN    = "#2ecc71"
GREEN_HV = "#33d97a"
RED      = "#e74c3c"
RED_HV   = "#ec6555"
GREY     = "#3a3c4f"


# ----------------------------------------------------------------------------- #
#  Права администратора
# ----------------------------------------------------------------------------- #
def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> None:
    """Перезапускает программу с правами администратора и закрывает текущую."""
    if getattr(sys, "frozen", False):
        exe, params = sys.executable, subprocess.list2cmdline(sys.argv[1:])
    else:
        exe = sys.executable
        params = subprocess.list2cmdline([os.path.abspath(sys.argv[0])] + sys.argv[1:])

    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
    if rc <= 32:  # пользователь отказал в UAC или ошибка
        ctypes.windll.user32.MessageBoxW(
            None,
            "Для работы программе нужны права администратора "
            "(этого требует драйвер WinDivert).\n\nЗапустите ещё раз и нажмите «Да».",
            APP_TITLE, 0x10)
    sys.exit(0)


# ----------------------------------------------------------------------------- #
#  Сеть / установка
# ----------------------------------------------------------------------------- #
def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def fetch_latest_release() -> tuple[str, str]:
    """Возвращает (tag, ссылка_на_zip) последнего релиза."""
    with urllib.request.urlopen(_request(API_LATEST), timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    tag = data["tag_name"]
    zip_asset = next(
        (a for a in data.get("assets", []) if a["name"].lower().endswith(".zip")),
        None)
    if not zip_asset:
        raise RuntimeError("В релизе не найден .zip-архив.")
    return tag, zip_asset["browser_download_url"]


def download_file(url: str, dest: str, progress=None) -> None:
    with urllib.request.urlopen(_request(url), timeout=120) as r:
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        with open(dest, "wb") as f:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done / total)


def find_bat_root(base: str) -> str | None:
    """Ищет папку, в которой лежит general.bat (внутри распакованного архива)."""
    for dirpath, _dirs, files in os.walk(base):
        if "general.bat" in files:
            return dirpath
    return None


def read_local_version() -> str | None:
    try:
        with open(VERSION_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def ensure_installed(status, progress) -> tuple[str, str]:
    """
    Гарантирует, что последний релиз скачан и распакован.
    Возвращает (папка_с_bat, версия). Работает офлайн, если уже что-то скачано.
    """
    os.makedirs(INSTALL_DIR, exist_ok=True)

    status("Проверяю обновления…")
    try:
        tag, zip_url = fetch_latest_release()
    except (urllib.error.URLError, OSError, RuntimeError):
        # Нет интернета / GitHub недоступен — пробуем то, что уже скачано
        root = find_bat_root(FILES_DIR)
        if root:
            status("Нет связи с GitHub — использую скачанную версию.")
            return root, read_local_version() or "?"
        raise RuntimeError("Нет интернета, и ничего ещё не скачано.\n"
                           "Подключитесь к сети и попробуйте снова.")

    # Уже установлена актуальная версия?
    root = find_bat_root(FILES_DIR)
    if root and read_local_version() == tag:
        status(f"Версия {tag} уже скачана.")
        return root, tag

    # Качаем заново
    status(f"Скачиваю версию {tag}…")
    if os.path.isdir(FILES_DIR):
        remove_dir_robust(FILES_DIR)
    os.makedirs(FILES_DIR, exist_ok=True)

    zip_path = os.path.join(INSTALL_DIR, "release.zip")
    download_file(zip_url, zip_path, progress)

    status("Распаковываю…")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(FILES_DIR)
    try:
        os.remove(zip_path)
    except OSError:
        pass

    root = find_bat_root(FILES_DIR)
    if not root:
        raise RuntimeError("В архиве не найден general.bat.")

    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(tag)
    return root, tag


def remove_dir_robust(path: str, attempts: int = 12) -> bool:
    """Удаляет папку с повторами — на случай, если файлы ещё заняты (winws/WinDivert)."""
    import shutil
    for _ in range(attempts):
        if not os.path.exists(path):
            return True
        try:
            shutil.rmtree(path)
        except OSError:
            time.sleep(0.5)
    return not os.path.exists(path)


# ----------------------------------------------------------------------------- #
#  Стратегии (ALT) и управление обходом
# ----------------------------------------------------------------------------- #
def latest_alt_bat(root: str) -> tuple[str, str] | None:
    """Находит ALT-стратегию с максимальным номером. Возвращает (путь, имя)."""
    best_path, best_name, best_n = None, None, -1
    pattern = re.compile(r"^general \(ALT(\d*)\)\.bat$", re.IGNORECASE)
    for name in os.listdir(root):
        m = pattern.match(name)
        if m:
            n = int(m.group(1)) if m.group(1) else 1
            if n > best_n:
                best_n, best_path, best_name = n, os.path.join(root, name), name
    if best_path:
        return best_path, best_name
    return None


def start_strategy(bat_path: str) -> None:
    folder = os.path.dirname(bat_path)
    env = dict(os.environ)
    env["NO_UPDATE_CHECK"] = "1"  # отключаем интерактивную проверку обновлений в bat
    subprocess.Popen(["cmd", "/c", bat_path], cwd=folder, env=env,
                     creationflags=CREATE_NO_WINDOW)


def stop_strategy() -> None:
    subprocess.run(["taskkill", "/F", "/IM", "winws.exe"],
                   creationflags=CREATE_NO_WINDOW,
                   capture_output=True)


def is_running() -> bool:
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq winws.exe", "/NH"],
        creationflags=CREATE_NO_WINDOW, capture_output=True, text=True).stdout
    return "winws.exe" in (out or "").lower()


# ----------------------------------------------------------------------------- #
#  Интерфейс
# ----------------------------------------------------------------------------- #
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.configure(bg=BG)
        self.resizable(False, False)
        self._busy = False
        self._build_ui()
        self._center(420, 420)

        # Периодически сверяем реальное состояние winws.exe с кнопкой
        self.after(500, self._sync_state)
        self.after(2500, self._poll_loop)

    # --- разметка ---------------------------------------------------------- #
    def _build_ui(self):
        tk.Label(self, text=APP_TITLE, bg=BG, fg=TEXT,
                 font=("Segoe UI Semibold", 15)).pack(pady=(22, 2))
        tk.Label(self, text="Обход блокировок Discord и YouTube",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack()

        # Большая кнопка-переключатель
        self.btn = tk.Button(self, text="Включить", font=("Segoe UI Semibold", 16),
                             bg=GREEN, fg="white", activebackground=GREEN_HV,
                             activeforeground="white", relief="flat", bd=0,
                             width=16, height=2, cursor="hand2",
                             command=self.on_toggle)
        self.btn.pack(pady=(26, 8))

        # Вторичная кнопка — проверка обновлений
        self.upd_btn = tk.Button(self, text="Проверить обновление",
                                 font=("Segoe UI", 10), bg=CARD, fg=TEXT,
                                 activebackground=GREY, activeforeground=TEXT,
                                 relief="flat", bd=0, cursor="hand2",
                                 padx=12, pady=6, command=self.on_check_update)
        self.upd_btn.pack(pady=(0, 12))

        # Прогресс
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Z.Horizontal.TProgressbar",
                        troughcolor=CARD, background=GREEN,
                        bordercolor=CARD, lightcolor=GREEN, darkcolor=GREEN)
        self.pbar = ttk.Progressbar(self, style="Z.Horizontal.TProgressbar",
                                    length=320, mode="determinate", maximum=100)
        self.pbar.pack(pady=(0, 6))
        self.pbar.pack_forget()

        # Статус
        self.status = tk.Label(self, text="Готово к запуску",
                               bg=BG, fg=MUTED, font=("Segoe UI", 10))
        self.status.pack(pady=(2, 4))

        self.version_lbl = tk.Label(self, text="", bg=BG, fg=MUTED,
                                    font=("Segoe UI", 8))
        self.version_lbl.pack()

        tk.Label(self, text="движок zapret (bol-van) · сборка Flowseal",
                 bg=BG, fg="#5a5c70", font=("Segoe UI", 8)).pack(side="bottom",
                                                                 pady=8)

    def _center(self, w, h):
        self.update_idletasks()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 3
        self.geometry(f"{w}x{h}+{x}+{y}")

    # --- помощники для обновления UI из потока ------------------------------ #
    def ui(self, fn, *a):
        self.after(0, lambda: fn(*a))

    # --- обработчик кнопки -------------------------------------------------- #
    def on_toggle(self):
        if self._busy:
            return
        if is_running():
            self._do_stop()
        else:
            self._do_start()

    def _do_stop(self):
        self._set_busy(True, "Выключаю…")
        def work():
            stop_strategy()
            self.ui(self._finish_off)
        threading.Thread(target=work, daemon=True).start()

    def _do_start(self):
        self._set_busy(True, "Подготовка…")
        self.ui(self._show_progress, True)

        def progress(frac):
            self.ui(self.pbar.config, {"value": int(frac * 100)})
            self.ui(self.status.config, {"text": f"Скачиваю… {int(frac*100)}%"})

        def status(text):
            self.ui(self.status.config, {"text": text})

        def work():
            try:
                root, version = ensure_installed(status, progress)
                self.ui(self.version_lbl.config, {"text": f"Версия {version}"})
                alt = latest_alt_bat(root)
                if not alt:
                    raise RuntimeError("Не найдена ни одна ALT-стратегия.")
                bat_path, bat_name = alt
                self.ui(self.status.config, {"text": f"Запускаю {bat_name}…"})
                start_strategy(bat_path)

                # Ждём появления winws.exe (до ~12 секунд)
                ok = False
                for _ in range(24):
                    if is_running():
                        ok = True
                        break
                    time.sleep(0.5)

                if ok:
                    self.ui(self._finish_on, bat_name)
                else:
                    self.ui(self._fail, "Не удалось запустить обход.\n"
                                        "Проверьте антивирус (он может блокировать "
                                        "WinDivert) и попробуйте ещё раз.")
            except Exception as e:  # noqa: BLE001
                self.ui(self._fail, str(e))

        threading.Thread(target=work, daemon=True).start()

    # --- проверка обновления ----------------------------------------------- #
    def on_check_update(self):
        if self._busy:
            return
        self._set_busy(True, "Проверяю обновления…")
        self.ui(self._show_progress, True)

        def progress(frac):
            self.ui(self.pbar.config, {"value": int(frac * 100)})
            self.ui(self.status.config, {"text": f"Скачиваю… {int(frac*100)}%"})

        def status(text):
            self.ui(self.status.config, {"text": text})

        def work():
            try:
                status("Проверяю обновления…")
                local = read_local_version()
                latest, _url = fetch_latest_release()
                has_files = find_bat_root(FILES_DIR) is not None

                # Уже последняя версия — ничего не трогаем
                if has_files and local == latest:
                    self.ui(self._update_uptodate, latest)
                    return

                # Есть обновление: выключить → удалить → скачать → включить
                status(f"Найдена версия {latest}. Обновляю…")
                if is_running():
                    status("Выключаю обход…")
                    stop_strategy()
                    for _ in range(20):           # ждём, пока winws закроется
                        if not is_running():
                            break
                        time.sleep(0.3)

                status("Удаляю старую версию…")
                if not remove_dir_robust(FILES_DIR):
                    raise RuntimeError(
                        "Не удалось удалить старую версию — файлы заняты.\n"
                        "Закройте обход и попробуйте снова.")

                root, version = ensure_installed(status, progress)
                self.ui(self.version_lbl.config, {"text": f"Версия {version}"})

                alt = latest_alt_bat(root)
                if not alt:
                    raise RuntimeError("Не найдена ни одна ALT-стратегия.")
                bat_path, bat_name = alt
                status(f"Запускаю {bat_name}…")
                start_strategy(bat_path)

                ok = False
                for _ in range(24):
                    if is_running():
                        ok = True
                        break
                    time.sleep(0.5)

                if ok:
                    self.ui(self._finish_update_on, version, bat_name)
                else:
                    self.ui(self._fail,
                            "Обновление скачано, но обход не запустился.\n"
                            "Проверьте антивирус (WinDivert) и попробуйте ещё раз.")
            except Exception as e:  # noqa: BLE001
                self.ui(self._fail, str(e))

        threading.Thread(target=work, daemon=True).start()

    def _update_uptodate(self, version):
        self._set_busy(False)
        self._show_progress(False)
        self.version_lbl.config(text=f"Версия {version}")
        self._sync_state()
        self.status.config(text=f"✓ Установлена последняя версия ({version})",
                           fg=GREEN)
        messagebox.showinfo(APP_TITLE,
                            f"У вас уже последняя версия: {version}")

    def _finish_update_on(self, version, bat_name):
        self._set_busy(False)
        self._show_progress(False)
        self.btn.config(text="Выключить", bg=RED, activebackground=RED_HV)
        self.status.config(text=f"✓ Обновлено до {version}  ({bat_name})", fg=GREEN)
        messagebox.showinfo(APP_TITLE,
                            f"Обновлено до версии {version}. Обход включён.")

    # --- состояния ---------------------------------------------------------- #
    def _set_busy(self, busy, text=None):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.btn.config(state=state)
        self.upd_btn.config(state=state)
        if busy:
            self.btn.config(bg=GREY, activebackground=GREY)
        if text:
            self.status.config(text=text)

    def _show_progress(self, show):
        if show:
            self.pbar.config(value=0)
            self.pbar.pack(before=self.status, pady=(0, 6))
        else:
            self.pbar.pack_forget()

    def _finish_on(self, bat_name):
        self._set_busy(False)
        self._show_progress(False)
        self.btn.config(text="Выключить", bg=RED, activebackground=RED_HV)
        self.status.config(text=f"✓ Обход работает  ({bat_name})", fg=GREEN)

    def _finish_off(self):
        self._set_busy(False)
        self._show_progress(False)
        self.btn.config(text="Включить", bg=GREEN, activebackground=GREEN_HV)
        self.status.config(text="Обход выключен", fg=MUTED)

    def _fail(self, msg):
        self._set_busy(False)
        self._show_progress(False)
        self.btn.config(text="Включить", bg=GREEN, activebackground=GREEN_HV)
        self.status.config(text="Ошибка", fg=RED)
        messagebox.showerror(APP_TITLE, msg)

    # --- фоновая синхронизация состояния ------------------------------------ #
    def _sync_state(self):
        if not self._busy:
            if is_running():
                self.btn.config(text="Выключить", bg=RED, activebackground=RED_HV)
                if not self.status.cget("text").startswith("✓"):
                    self.status.config(text="✓ Обход работает", fg=GREEN)
            else:
                self.btn.config(text="Включить", bg=GREEN, activebackground=GREEN_HV)

    def _poll_loop(self):
        self._sync_state()
        self.after(2500, self._poll_loop)


def main():
    if not is_admin():
        relaunch_as_admin()
        return
    App().mainloop()


if __name__ == "__main__":
    main()

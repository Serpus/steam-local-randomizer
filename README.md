# 🎲 Steam Local Randomizer

Устали думать, во что поиграть? **Steam Local Randomizer** находит установленный Steam,
сканирует **все** ваши библиотеки (включая игры на других дисках) и выбирает игру за вас.
Никаких Steam API-ключей, аккаунтов и интернета — всё работает локально.

## ✨ Возможности

- 🔍 Автоматически находит установленный Steam (Windows и Linux).
- 📚 Читает игры **во всех** библиотеках, а не только в основной папке.
- 🎯 Работает с играми на внешних дисках и SSD.
- 🚫 Автоматически исключает инструменты (Proton, SteamVR, Steam Linux Runtime, Redistributables, Wallpaper Engine).
- 🎰 **Эффект рулетки** — при нажатии «Крутить!» игры быстро перебираются, затем плавно замедляются и останавливаются на одной.
- 🎮 **Крутить и запустить** — выбор и мгновенный запуск игры в один клик.
- 📋 **Все игры** — список всех установленных игр с кнопкой запуска у каждой.
- 🌐 **Вся библиотека** — опциональная загрузка всех ваших игр (даже не установленных) через Steam API.
- 🖥 Две версии: **GUI** (окно с кнопкой) и **CLI** (командная строка для скриптов).
- 🐧 Работает на **Windows** и **Linux** (включая SteamOS / Steam Deck).

## 📥 Скачать

Скачайте последний релиз со страницы **Releases**:

### 🪟 Windows
- **`steam-randomizer-gui-windows.exe`** — обычная версия с окном. Двойной клик — и готово.
- **`steam-randomizer-windows.exe`** — консольная версия для скриптов и автозапуска.

Установка Python и других программ **не требуется** — всё уже внутри.

> ⚠️ При первом запуске Windows SmartScreen может показать предупреждение
> («Windows защитила ваш компьютер»). Нажмите **«Подробнее» → «Выполнить в любом случае»** —
> это стандартное поведение для неподписанных `.exe`. Код открыт, вы можете проверить
> его самостоятельно или собрать `.exe` самому.

### 🐧 Linux
- **`steam-randomizer-gui-linux`** — GUI версия с окном.
- **`steam-randomizer-linux`** — консольная версия для скриптов.

**Как запустить:**
```bash
# Сделайте файл исполняемым (только в первый раз)
chmod +x steam-randomizer-gui-linux

# Запустите
./steam-randomizer-gui-linux
```

**Системные требования:**
- Установленный Steam (из пакетного менеджера дистрибутива, Flatpak или с официального сайта).
- Для GUI-версии нужен установленный пакет `python3-tk` (обычно уже стоит в системе, если установлен Python с Tkinter):
  - **Ubuntu / Debian / Mint:** `sudo apt install python3-tk`
  - **Fedora:** `sudo dnf install python3-tkinter`
  - **Arch Linux:** `sudo pacman -S tk`

> 💡 Приложение поддерживает установку Steam через **Flatpak** (`com.valvesoftware.Steam`) и стандартную установку в `~/.steam/steam` или `~/.local/share/Steam`.

## 🚀 Использование

### GUI (графическое окно)

Запустите `steam-randomizer-gui.exe` (Windows) или `./steam-randomizer-gui-linux` (Linux). Появится тёмное окно:

- **🎲 Крутить!** — запустить рулетку: игры быстро перебираются и плавно замедляются до остановки.
- **▶ Запустить** — запустить выбранную игру.
- **🎲▶ Крутить и запустить** — выбрать и запустить игру в один клик.
- **📋 Все игры** — открыть список всех установленных игр с кнопкой ▶ у каждой.
- **☑ Вся библиотека** — загрузить **все** ваши игры из Steam (даже не установленные) через официальный API без ключа.

В строке статуса видно, сколько игр найдено в библиотеке.

### CLI (командная строка)

Для продвинутых пользователей и скриптов — `steam-randomizer.exe` (Windows) или `./steam-randomizer-linux` (Linux):

```bash
steam-randomizer                  # выбрать случайную игру
steam-randomizer --list           # показать список всех установленных игр
steam-randomizer --include-tools  # включить Proton, SteamVR и т.п. в пул
steam-randomizer --version        # версия
```

Пример вывода:

```
Steam found at: C:\Program Files (x86)\Steam
Pool size: 42 games

🎲 Your random game: Hades (appid 1145360)
```

## 🛠 Как это работает

1. **Поиск Steam.**
   - **Windows:** читает ключ `SteamPath` из реестра
     `HKEY_CURRENT_USER\Software\Valve\Steam`. Если ключа нет — пробует стандартные пути
     `C:\Program Files (x86)\Steam` и `C:\Program Files\Steam`.
   - **Linux:** проверяет стандартные пути в порядке приоритета:
     `~/.steam/steam`, `~/.local/share/Steam`, Flatpak-установка (`com.valvesoftware.Steam`), `/usr/share/steam`.
2. **Поиск библиотек.** Парсит `steamapps/libraryfolders.vdf` и получает список
   **всех** папок с играми (включая другие диски и внешние SSD).
3. **Сканирование.** В каждой библиотеке находит файлы `appmanifest_*.acf`
   и достаёт название игры и её `appid`.
4. **Фильтрация.** Исключает служебные записи: Proton, SteamVR,
   Steam Linux Runtime, Steamworks Common Redistributables, Wallpaper Engine.
5. **Выбор.** Берёт случайную игру из отфильтрованного пула.
   Запуск — через URI `steam://rungameid/<appid>`:
   - **Windows:** `os.startfile()`
   - **Linux:** `xdg-open` (с fallback на бинарник `steam` или `flatpak run com.valvesoftware.Steam`).

Всё происходит **локально** на вашем компьютере. Программа не подключается к интернету
и не отправляет никаких данных. Единственное исключение — опция «Вся библиотека»,
которая обращается к публичному Steam API (без ключа) для получения названий игр.

## 🧑‍💻 Сборка из исходников

### Windows

Запустите `build.bat` двойным кликом. Скрипт:
- создаст виртуальное окружение `.venv`,
- установит все зависимости из `pyproject.toml`,
- прогонит `pytest`,
- соберёт два `.exe` в папке `dist/`:
  - `dist/steam-randomizer-gui.exe`
  - `dist/steam-randomizer.exe`

### Linux

```bash
# 1. Установите системные зависимости
sudo apt install python3-tk patchelf   # Ubuntu / Debian / Mint
# sudo dnf install python3-tkinter patchelf   # Fedora
# sudo pacman -S tk patchelf                  # Arch Linux

# 2. Сделайте скрипт исполняемым
chmod +x build_linux.sh

# 3. Запустите сборку
./build_linux.sh
```

Скрипт:
- создаст виртуальное окружение `.venv`,
- установит все зависимости,
- прогонит `pytest`,
- соберёт два исполняемых файла в папке `dist/`:
  - `dist/steam-randomizer-gui`
  - `dist/steam-randomizer`

> 💡 `patchelf` нужен PyInstaller для корректной упаковки shared-библиотек (`.so`) в режим `--onefile`.
> Без него собранный бинарник может не запуститься на системах с другой версией `glibc`.

### CI / Автоматическая сборка

Каждый push тега `v*` запускает GitHub Actions, который:
1. Параллельно собирает билды под **Windows** (`windows-latest`) и **Linux** (`ubuntu-latest`).
2. Запускает тесты на обеих платформах.
3. Автоматически создаёт GitHub Release и прикрепляет 4 файла:
   - `steam-randomizer-gui-windows.exe`
   - `steam-randomizer-windows.exe`
   - `steam-randomizer-gui-linux`
   - `steam-randomizer-linux`

## 📄 Лицензия

MIT — используйте, форкайте, изменяйте как угодно.

## 🙏 Благодарности

- **[vdf](https://github.com/rossengeorgiev/vdf-python)** — парсинг Valve Data Format.
- **[CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)** — современный GUI для Tkinter.
- **[PyInstaller](https://pyinstaller.org/)** — упаковка в standalone-бинарники.
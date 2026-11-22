# 🎲 Steam Local Randomizer

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.5-blue)](https://github.com/Serpus/steam-local-randomizer/releases)
[![Build](https://github.com/Serpus/steam-local-randomizer/actions/workflows/release.yml/badge.svg)](https://github.com/Serpus/steam-local-randomizer/actions/workflows/release.yml)
[![Issues](https://img.shields.io/github/issues/Serpus/steam-local-randomizer)](https://github.com/Serpus/steam-local-randomizer/issues)
[![Скриншот Steam Local Randomizer](docs/screenshot.png)](docs/screenshot.png)

Устали думать, во что поиграть? **Steam Local Randomizer** находит установленный Steam,
сканирует **все** ваши библиотеки и выбирает игру за вас. Никаких Steam API-ключей,
аккаунтов и регистрации — всё работает локально.

![Скриншот Steam Local Randomizer](docs/screenshot.png)

## ✨ Возможности

- 🔍 Автоматически находит установленный Steam.
- 📚 Читает игры **во всех** библиотеках, а не только в основной папке.
- 🎯 Работает с играми на внешних дисках и SSD.
- 🚫 Автоматически исключает инструменты (Proton, SteamVR, Steam Linux Runtime, Redistributables, Wallpaper Engine).
- 🎰 **Эффект рулетки** — при нажатии «Крутить!» игры быстро перебираются, затем плавно замедляются и останавливаются на одной.
- 🎮 **Крутить и запустить** — выбор и мгновенный запуск игры в один клик.
- 📋 **Все игры** — список всех установленных игр с кнопкой запуска у каждой.
- 📚 **Вся библиотека** — переключатель, который включает в выборку не только установленные игры, но и все купленные в Steam (включая те, что сейчас не установлены).
- 🖥 Две версии: **GUI** (окно с кнопкой) и **CLI** (командная строка для скриптов).

## 📥 Скачать

Скачайте последний `.exe` со страницы [**Releases**](https://github.com/Serpus/steam-local-randomizer/releases):

- **`steam-randomizer-gui.exe`** — обычная версия с окном. Двойной клик — и готово.
- **`steam-randomizer.exe`** — консольная версия для скриптов и автозапуска.

Установка Python и других программ **не требуется** — всё уже внутри.

> ⚠️ При первом запуске Windows SmartScreen может показать предупреждение
> («Windows защитила ваш компьютер»). Нажмите **«Подробнее» → «Выполнить в любом случае»** —
> это стандартное поведение для неподписанных `.exe`. Код открыт, вы можете проверить
> его самостоятельно или собрать `.exe` самому.

## 🚀 Использование

### GUI (графическое окно)

Запустите `steam-randomizer-gui.exe`. Появится тёмное окно:

- **🎲 Крутить!** — запустить рулетку: игры быстро перебираются и плавно замедляются до остановки.
- **▶ Запустить** — запустить выбранную игру.
- **🎲▶ Крутить и запустить** — выбрать и запустить игру в один клик.
- **📋 Все игры** — открыть список всех игр с кнопкой ▶ у каждой.
- **Вся библиотека** — чекбокс под шапкой. При включении загружает полный список купленных игр из локальных файлов Steam и Steam Store API. Неустановленные игры помечаются «· не установлена» в списке.

В строке статуса видно, сколько игр найдено в библиотеке.

> ℹ️ Названия **неустановленных** игр подгружаются из Steam Store API при первом включении чекбокса и кэшируются на 7 дней в `%APPDATA%\steam-local-randomizer\`. Если интернета нет — приложение **молча** откатывается на локальные данные (манифесты + реестр Windows), игры без названия отображаются как `App <id>`. Никаких ошибок и зависаний.
>
> 💡 Названия **некоторых** (менее 5%) неустановленных игр могут отображаться как `App <id>` — обычно это удалённые из магазина игры или скрытые сервисные приложения. Для 95%+ библиотеки названия подгружаются корректно.

### CLI (командная строка)

Для продвинутых пользователей и скриптов — `steam-randomizer.exe`:

```
steam-randomizer.exe                  # выбрать случайную игру
steam-randomizer.exe --list           # показать список всех установленных игр
steam-randomizer.exe --include-tools  # включить Proton, SteamVR и т.п. в пул
steam-randomizer.exe --version        # версия
```

Пример вывода:

```
Steam found at: C:\Program Files (x86)\Steam
Pool size: 42 games

🎲 Your random game: Hades (appid 1145360)
```

## 🛠 Как это работает

1. **Поиск Steam.** Читает ключ `SteamPath` из реестра
   `HKEY_CURRENT_USER\Software\Valve\Steam`. Если ключа нет — пробует стандартные пути
   `C:\Program Files (x86)\Steam` и `C:\Program Files\Steam`.
2. **Поиск библиотек.** Парсит `steamapps/libraryfolders.vdf` и получает список
   **всех** папок с играми (включая другие диски и внешние SSD).
3. **Сканирование.** В каждой библиотеке находит файлы `appmanifest_*.acf`
   и достаёт название игры и её `appid`.
4. **Фильтрация.** Исключает служебные записи: Proton, SteamVR,
   Steam Linux Runtime, Steamworks Common Redistributables, Wallpaper Engine.
5. **Выбор.** Берёт случайную игру из отфильтрованного пула.
   Запуск — через URI `steam://rungameid/<appid>`.
6. **Полная библиотека (опционально).** Если включён чекбокс «Вся библиотека»,
   читается `userdata/<id>/config/localconfig.vdf` — список всех приложений пользователя.
   Названия подтягиваются из трёх источников (в порядке приоритета):
   - `appmanifest_*.acf` — для установленных игр;
   - реестр Windows (`HKCU\Software\Valve\Steam\Apps\<id>\Name`) — для ранее запускавшихся;
   - Steam Store API (`IStoreBrowseService/GetItems`) — для остальных, с кэшем на 7 дней.

Всё остальное происходит **локально**. В интернет приложение обращается только при первом
включении чекбокса «Вся библиотека» — чтобы подгрузить названия игр, которых нет на диске.
Если интернета нет, всё работает без ошибок.

## 📄 Лицензия

[MIT](LICENSE) — используйте, форкайте, изменяйте как угодно.

## 🙏 Благодарности

- [vdf](https://pypi.org/project/vdf/) — парсинг Valve Data Format.
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — современный GUI для Tkinter.
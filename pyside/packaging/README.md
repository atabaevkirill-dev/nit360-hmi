# Сборка релиза NIT-360 HMI (версия на PySide6)

PyInstaller не умеет кросс-компиляцию: **Windows-exe собирается только на Windows,
AppImage — только на Linux**. Конфигурация одна на обе цели —
[`pyside/nit360.spec`](../nit360.spec); скрипты ниже просто вызывают её с нужным режимом.

## Windows → портативный exe

На Windows-машине с Python 3.11+ ([python.org](https://www.python.org/downloads/), при
установке отметить «Add python.exe to PATH»), из корня репозитория:

```powershell
powershell -ExecutionPolicy Bypass -File pyside\packaging\build_windows.ps1
```

Скрипт создаёт окружение `.venv-build`, ставит PySide6 + pyserial + PyInstaller и собирает
**`dist\NIT-360-HMI.exe`** — один файл, ~60–80 МБ, ничего доустанавливать на целевой
машине не нужно. Первый запуск занимает несколько секунд: onefile распаковывает Qt
во временный каталог. Если это мешает, соберите каталогом:

```powershell
$env:NIT360_BUILD_MODE = "onedir"
.venv-build\Scripts\python.exe -m PyInstaller pyside\nit360.spec --noconfirm --clean
```

— получится `dist\NIT-360-HMI\` (запускать `NIT-360-HMI.exe` внутри), стартует мгновенно.

Что стоит знать:

- exe не подписан, поэтому Windows SmartScreen при первом запуске покажет «Неизвестный
  издатель» → «Подробнее» → «Выполнить в любом случае». Убирается только покупкой
  сертификата подписи кода.
- Драйвер USB↔RS-422 (CH340, FTDI, Prolific) ставится отдельно — в exe его нет.

## Linux → AppImage

На Linux x86_64 с Python 3.11+, `curl` и правами на запуск AppImage:

```bash
./pyside/packaging/build_linux.sh
```

Результат — **`dist/NIT-360-HMI-x86_64.AppImage`**. Скрипт сам скачает `appimagetool`
в `pyside/packaging/tools/` (только при первом запуске) и вызовет его с
`--appimage-extract-and-run`, чтобы сборка шла и на машинах без FUSE.

Запуск у пользователя:

```bash
chmod +x NIT-360-HMI-x86_64.AppImage
./NIT-360-HMI-x86_64.AppImage
```

Что стоит знать:

- Доступ к последовательному порту: пользователь должен быть в группе `dialout`
  (`sudo usermod -aG dialout $USER`, затем перелогиниться), иначе порт не откроется и в
  журнале будет «Не удалось открыть порт: Permission denied».
- Собирать нужно на дистрибутиве с glibc не новее целевого: сборка на Ubuntu 22.04
  запустится на 22.04 и новее, но не на 20.04. Для широкой совместимости берите
  самый старый поддерживаемый дистрибутив.
- Для запуска AppImage у пользователя нужен FUSE (`libfuse2` в Ubuntu 22.04+) либо
  распаковка: `./NIT-360-HMI-x86_64.AppImage --appimage-extract`.

## Проверка собранного приложения без прибора

```bash
dist/NIT-360-HMI --version                       # печатает версию и выходит
dist/NIT-360-HMI --demo                          # окно сразу в демо-режиме
QT_QPA_PLATFORM=offscreen NIT360_DEMO_HOURS=12500 \
  dist/NIT-360-HMI --demo --screenshot вид.png   # снимок без экрана
```

`--screenshot` и `NIT360_DEMO_HOURS` работают и в сборке — так проверяются подсветка
«ВНЕ ГАРАНТИИ» и общий вид без железа.

## Иконки

`pyside/assets/icon.png` (Linux, окно) и `icon.ico` (Windows, exe) лежат в репозитории.
Перерисовать: `QT_QPA_PLATFORM=offscreen python pyside/make_icon.py`.

## macOS

Отдельной целью не является. Локально спека собирается (`pyinstaller pyside/nit360.spec`)
и годится как проверка конфигурации, но `.app` не подписан и не нотаризован, а иконки
у него нет — для релиза macOS понадобится `.icns` и подпись.

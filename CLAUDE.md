# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Общение с пользователем — на русском, кратко и по делу. Код и комментарии в этом проекте тоже на русском.

## Команды

```bash
npm install          # node_modules не в репозитории
npm start            # Electron-приложение
npm run dev          # интерфейс на http://localhost:3000 + сервис RS-422 на 3003 (отладка в браузере)
npm test             # тесты кодека протокола (scripts/test-protocol.js)
npm run sync:client  # обновить renderer/vendor/socket.io.min.js из node_modules
npm run build:exe        # electron-builder --win  → portable x64
npm run build:appimage   # electron-builder --linux → AppImage x64
```

Один тест отдельно не запускается — набор маленький, `npm test` гоняет все семь проверок.

`serialport` — нативный модуль, ставится под текущую платформу. Если npm заблокировал install-скрипты (`npm warn allow-scripts`), бинарник Electron не распакуется и `npm start` упадёт с `electron: command not found`; лечится `npm approve-scripts` либо ручной распаковкой zip из `~/Library/Caches/electron` в `node_modules/electron/dist` + записью `path.txt`.

## Архитектура

HMI-пульт для тепловизора NIT-360 по USB↔RS-422. Интерфейс полностью на русском.

- [electron/serial-service.js](electron/serial-service.js) — вся серверная логика: кодек протокола, транспорт, Socket.IO-сервис. Используется и Electron-процессом, и dev-сервером, поэтому дублировать протокол где-либо ещё не нужно.
- [electron/main.js](electron/main.js) — только окно и запуск сервиса.
- [renderer/](renderer/) — интерфейс на чистых HTML/CSS/JS, **без сборки**. Клиент Socket.IO лежит в `renderer/vendor/`, чтобы страница работала и по `file://`, и по HTTP.
- [scripts/dev-server.js](scripts/dev-server.js) — статика `renderer/` + тот же сервис, нужен только для отладки в браузере.

### Протокол

Кадр 7 байт: `FF <id> 00 <code> <param> 00 <xor байтов 1..5>`. Ответ такой же длины. Таблица `COMMANDS` сопоставляет строковые id опкодам.

Байт `data[4]` перегружен: у обычных команд это статус (`0x01` — успех), а у команд-запросов данных — старший байт 16-битного значения (`data[4]<<8 | data[5]`). Поэтому `parseResponse`/`parse_response` принимают опкод запроса и сверяются со списком `DATA_REPLY_CODES` (сейчас в нём только `get_runtime`, `0xB5`). Проверять статус у такого ответа нельзя: наработка 1274 ч даёт старший байт `0x04` и ответ ложно считался бы отклонённым, а 300 ч (`0x012C`) — «успешным» случайно. Если появятся другие команды чтения, добавлять их опкоды в этот же список.

Ресурс прибора — `WARRANTY_HOURS = 10000`: строго выше него наработка подсвечивается красным и помечается «ВНЕ ГАРАНТИИ» (ровно 10 000 ч — ещё в гарантии). Порог задан в обеих реализациях, значения должны совпадать. Проверить пороги без прибора помогает `NIT360_DEMO_HOURS` — эмулятор вернёт указанную наработку:

```bash
NIT360_DEMO_HOURS=12500 QT_QPA_PLATFORM=offscreen ./.venv/bin/python pyside/main.py --demo --screenshot вид.png
PORT=3010 NIT360_IO_PORT=3013 NIT360_DEMO_HOURS=12500 node scripts/dev-server.js
```

`FrameParser` собирает поток байтов в кадры по 7 и ресинхронизируется по `0xFF` — не полагаться на то, что ответ придёт одним куском. `Transport` держит FIFO-очередь: одна команда в эфире за раз, таймаут 2000 мс, ответ сверяется с опкодом запроса. Это важно при автоповторе кнопок с удержанием — иначе ответы разъезжаются с запросами.

Демо-режим (`DemoDevice`, путь порта `DEMO`) отвечает валидными кадрами без железа — им проверяется интерфейс и он же остаётся в списке портов, когда COM-портов нет.

### Контракт Socket.IO (порт 3003, `NIT360_IO_PORT`)

Renderer → сервис: `get_ports`, `connect_port({path, baud, id})`, `disconnect_port`, `send_command(cmdId)`, `set_id`, `set_baud`, `set_language`, `get_runtime`.
Сервис → renderer: `state`, `connection_status`, `ports_list`, `log`, `command_ok`, `command_result`, `runtime`, `error`.

`deviceState` — оптимистичное зеркало прибора: поле меняется только после успешного ответа. Прибор не опрашивается, поэтому состояние разойдётся, если крутить настройки с его собственной панели.

### Переменные окружения

`NIT360_IO_PORT` — порт сервиса, `NIT360_UI_URL` — загрузить интерфейс с URL вместо файла, `NIT360_DEVTOOLS=1` — открыть DevTools.

## Версия на PySide6 (pyside/)

Параллельная реализация того же пульта нативным Qt. Решением от 2026-09-05 доведена до релиза: настроена сборка exe и AppImage (см. «Сборка релиза» ниже). Electron-версия остаётся как есть.

```bash
python3 -m venv .venv && ./.venv/bin/python -m pip install -r pyside/requirements.txt
./.venv/bin/python pyside/main.py                      # окно
./.venv/bin/python pyside/main.py --demo               # сразу в демо-режиме
./.venv/bin/python pyside/test_protocol.py             # тесты кодека
QT_QPA_PLATFORM=offscreen ./.venv/bin/python pyside/main.py --demo --screenshot вид.png
```

`--screenshot` рендерит окно в PNG и выходит — так интерфейс проверяется без доступа к экрану. `--version` печатает версию и выходит, не создавая окна, — это smoke-тест собранного бинарника.

Здесь нет ни Socket.IO, ни отдельного сервиса: [pyside/link.py](pyside/link.py) живёт в `QThread` и общается с портом синхронно (write → read с таймаутом 2 с). Команды сериализуются самой очередью сигналов Qt, отдельная очередь не нужна; ответ всё равно сверяется с опкодом запроса. Кодек и эмулятор — [pyside/protocol.py](pyside/protocol.py), полный порт JS-версии.

Стиль — [pyside/style.qss](pyside/style.qss). Важно: глобальный `QWidget` не задаёт `background`, иначе каждая `QLabel` рисует плашку поверх панели; фон задают только контейнеры (`QWidget#Root`, `QFrame#Panel`, `QFrame#Topbar`, `QFrame#Statusbar`).

### Сборка релиза

Одна спека на обе цели — [pyside/nit360.spec](pyside/nit360.spec), режим задаётся `NIT360_BUILD_MODE` (`onefile` по умолчанию, `onedir` нужен AppImage). PyInstaller не кросс-компилирует: exe собирается только на Windows, AppImage только на Linux, поэтому скрипты запускаются на целевой ОС:

```bash
powershell -ExecutionPolicy Bypass -File pyside\packaging\build_windows.ps1   # → dist\NIT-360-HMI.exe
./pyside/packaging/build_linux.sh                                             # → dist/NIT-360-HMI-x86_64.AppImage
```

Подробности, подводные камни (SmartScreen, группа `dialout`, glibc) — [pyside/packaging/README.md](pyside/packaging/README.md).

Ресурсы внутри сборки лежат в `sys._MEIPASS`, поэтому `style.qss` и иконка открываются только через `resource_path()` из [pyside/resources.py](pyside/resources.py) — `Path(__file__).with_name(...)` в собранном приложении не работает. Иконки (`pyside/assets/icon.png`, `icon.ico`) сгенерированы [pyside/make_icon.py](pyside/make_icon.py) и лежат в репозитории; перегенерировать нужно только при смене рисунка.

В `excludes` спеки нельзя добавлять `shiboken6.Shiboken` — без него собранное приложение падает на импорте PySide6. QtQml/QtQuick/QtVirtualKeyboard приезжают как зависимость платформенных плагинов даже при исключении их Python-модулей; это нормально.

## Устаревшее

`out/` — сломанный экспорт Next.js от предыдущей версии интерфейса: в нём нет ни одного файла из `_next/static/chunks/`, исходников Next.js в репозитории тоже нет. Он больше нигде не используется и не попадает в сборку; можно удалить.

## Параметры прибора

9600 бод, 8N1, ID `0x09`. Смена скорости уходит кодом (`2400`→`0x00`, `9600`→`0x01`, `19200`→`0x02`), локальная скорость порта меняется только после подтверждения прибора — после этого нужно переподключиться.

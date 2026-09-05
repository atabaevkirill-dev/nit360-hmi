╔═══════════════════════════════════════════════════════════╗
║           NIT-360 HMI — Desktop Application               ║
║       Управление тепловизором NIT-360 через RS-422          ║
╚═══════════════════════════════════════════════════════════╝

УСТАНОВКА И ЗАПУСК (одна команда):
  npm install
  npm start

Готово! Откроется окно приложения с HMI-интерфейсом.

СБОРКА .EXE / .AppImage (версия на Electron):
  npm install
  npm run build:exe      (Windows)
  npm run build:appimage (Linux)

ВЕРСИЯ НА PYTHON/QT (pyside/) — запуск из исходников:
  python3 -m venv .venv
  ./.venv/bin/python -m pip install -r pyside/requirements.txt
  ./.venv/bin/python pyside/main.py

СБОРКА .EXE / .AppImage (версия на Python/Qt):
  Windows:  powershell -ExecutionPolicy Bypass -File pyside\packaging\build_windows.ps1
            → dist\NIT-360-HMI.exe (один файл, ничего доустанавливать не нужно)
  Linux:    ./pyside/packaging/build_linux.sh
            → dist/NIT-360-HMI-x86_64.AppImage
  Собирать нужно на целевой ОС — PyInstaller не кросс-компилирует.
  Подробности: pyside/packaging/README.md

ТРЕБОВАНИЯ:
  - Node.js 18+ (https://nodejs.org)
  - Для USB-RS422: драйверы преобразователя (CH340, FTDI и т.д.)

ПОДКЛЮЧЕНИЕ К ТЕПЛОВИЗОРУ:
  1. Подключите USB-RS422 преобразователь к компьютеру
  2. В приложении выберите COM-порт из списка или введите вручную
  3. Установите скорость 9600 бод и ID устройства (по умолчанию 9)
  4. Нажмите "Подключить"

ПАРАМЕТРЫ ПО УМОЛЧАНИЮ NIT-360:
  - Скорость: 9600 бод
  - Формат: 8N1
  - ID устройства: 9 (0x09)
  - Протокол: 7-байтовые кадры, XOR-контрольная сумма
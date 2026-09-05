# -*- mode: python ; coding: utf-8 -*-
"""Сборка PyInstaller. Запускать из корня репозитория:

    pyinstaller pyside/nit360.spec --noconfirm

Кросс-компиляции у PyInstaller нет: exe собирается только на Windows,
Linux-сборка — только на Linux. Режим задаётся переменной окружения
NIT360_BUILD_MODE: onefile (по умолчанию) или onedir — второй нужен AppImage.
"""
import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve()          # каталог pyside/
ONEDIR = os.environ.get("NIT360_BUILD_MODE", "onefile") == "onedir"

datas = [
    (str(ROOT / "style.qss"), "."),
    (str(ROOT / "assets" / "icon.png"), "assets"),
]

# Лишние подсистемы Qt. Исключения действуют на Python-модули; часть библиотек
# (QtQml, QtQuick, QtVirtualKeyboard) всё равно приезжает как зависимость плагинов
# платформы — это нормально, удалять их из a.binaries вручную не стоит.
excludes = [
    "tkinter", "unittest", "pydoc_data",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.Qt3DCore",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtBluetooth",
    "PySide6.QtPositioning", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtNetworkAuth", "PySide6.QtRemoteObjects", "PySide6.QtSensors",
    "PySide6.QtSerialBus", "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech",
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],                  # плоские импорты link/protocol/widgets
    binaries=[],
    datas=datas,
    hiddenimports=["serial.tools.list_ports"],
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# Windows берёт иконку из .ico внутри exe; Linux — из .desktop в AppImage,
# macOS требует .icns и релизной целью не является, поэтому там иконки нет
icon = str(ROOT / "assets" / "icon.ico") if sys.platform == "win32" else None
exe_kwargs = dict(
    name="NIT-360-HMI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                           # UPX ломает подпись и антивирусы к нему придираются
    console=False,                       # GUI: без окна консоли на Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)

if ONEDIR:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **exe_kwargs)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="NIT-360-HMI")
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], runtime_tmpdir=None, **exe_kwargs)

if sys.platform == "darwin":
    # только для локальной проверки сборки на Mac — релизные цели Windows и Linux
    app = BUNDLE(
        coll if ONEDIR else exe,
        name="NIT-360 HMI.app",
        bundle_identifier="com.nit360.hmi",
        info_plist={"NSHighResolutionCapable": True, "CFBundleShortVersionString": "1.0.0"},
    )

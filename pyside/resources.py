"""Пути к файлам-ресурсам: одинаково работают из исходников и из сборки PyInstaller."""
from __future__ import annotations

import sys
from pathlib import Path


def resource_path(name: str) -> Path:
    """Ресурс рядом с исходниками, а в собранном приложении — во временной
    распаковке PyInstaller (``sys._MEIPASS``)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / name
    return Path(__file__).resolve().parent / name


def is_frozen() -> bool:
    """True, если код выполняется из сборки PyInstaller."""
    return getattr(sys, "frozen", False)

"""Генератор иконок приложения: PNG для Linux и многоразмерный ICO для Windows.

Запуск (иконки лежат в репозитории, перегенерировать нужно только при смене рисунка):

    QT_QPA_PLATFORM=offscreen python pyside/make_icon.py
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication

ASSETS = Path(__file__).resolve().parent / "assets"
ICO_SIZES = (16, 32, 48, 64, 128, 256)

BG = QColor("#0e1620")
FRAME = QColor("#24333f")
ACCENT = QColor("#23c8a0")
TEXT = QColor("#e8f2ff")


def render(size: int) -> QImage:
    """Прицел на тёмной плашке; мелкие размеры рисуются без подписи."""
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    k = size / 256.0

    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    p.setBrush(BG)
    p.setPen(QPen(FRAME, max(1.0, 4 * k)))
    p.drawRoundedRect(QRectF(2 * k, 2 * k, size - 4 * k, size - 4 * k), 44 * k, 44 * k)

    # кольцо прицела и штрихи по сторонам
    center = size / 2.0
    ring = 74 * k
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(ACCENT, max(1.0, 9 * k)))
    p.drawEllipse(QRectF(center - ring, center - ring * 0.92, ring * 2, ring * 2 * 0.92))

    p.setPen(QPen(ACCENT, max(1.0, 9 * k), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    cy = center - ring * 0.08
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        x1 = center + dx * ring * 0.62
        y1 = cy + dy * ring * 0.58
        p.drawLine(QPointF(x1, y1), QPointF(x1 + dx * 30 * k, y1 + dy * 28 * k))

    p.setPen(QPen(ACCENT, max(1.0, 12 * k), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawPoint(QPointF(center, cy))

    if size >= 48:
        font = QFont()
        font.setBold(True)
        font.setPixelSize(int(38 * k))
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3 * k)
        p.setFont(font)
        p.setPen(TEXT)
        p.drawText(
            QRectF(0, size - 68 * k, size, 46 * k),
            Qt.AlignmentFlag.AlignCenter,
            "NIT360",
        )
    p.end()
    return image


def png_bytes(image: QImage) -> bytes:
    # QByteArray держим в переменной: временный объект QBuffer не продлевает ему жизнь
    store = QByteArray()
    buffer = QBuffer(store)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(store)


def write_ico(path: Path, images: dict[int, bytes]) -> None:
    """ICO с PNG внутри — Windows Vista и новее читают такой контейнер."""
    sizes = sorted(images)
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = len(header) + 16 * len(sizes)
    entries, blobs = b"", b""
    for size in sizes:
        data = images[size]
        entries += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,   # 0 означает 256
            0 if size >= 256 else size,
            0, 0, 1, 32, len(data), offset,
        )
        blobs += data
        offset += len(data)
    path.write_bytes(header + entries + blobs)


def main() -> int:
    QApplication(sys.argv)
    ASSETS.mkdir(exist_ok=True)

    images = {size: png_bytes(render(size)) for size in ICO_SIZES}
    (ASSETS / "icon.png").write_bytes(images[256])
    write_ico(ASSETS / "icon.ico", images)
    print(f"записано: {ASSETS / 'icon.png'}, {ASSETS / 'icon.ico'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

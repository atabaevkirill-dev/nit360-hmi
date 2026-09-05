"""Мелкие виджеты HMI: светодиод, панель, поле, сегментный переключатель."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

LED_COLORS = {
    "off": QColor("#1b2733"),
    "on": QColor("#23c8a0"),
    "warn": QColor("#f0a848"),
    "error": QColor("#e5484d"),
}


class Led(QWidget):
    """Индикатор-светодиод с ореолом свечения."""

    def __init__(self, state: str = "off") -> None:
        super().__init__()
        self._state = state
        self.setFixedSize(14, 14)

    def set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 — имя из Qt
        color = LED_COLORS.get(self._state, LED_COLORS["off"])
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._state != "off":
            glow = QColor(color)
            glow.setAlpha(70)
            p.setBrush(glow)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(0, 0, 14, 14)
        p.setBrush(color)
        p.setPen(QColor("#24333f"))
        p.drawEllipse(3, 3, 8, 8)


class Panel(QFrame):
    """Рамка с заголовком; содержимое кладётся в self.body."""

    def __init__(self, title: str, extra: QWidget | None = None) -> None:
        super().__init__()
        self.setObjectName("Panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        head = QWidget()
        head_row = QHBoxLayout(head)
        head_row.setContentsMargins(0, 0, 8, 0)
        head_row.setSpacing(6)
        label = QLabel(f"▍{title}")
        label.setObjectName("PanelTitle")
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        head_row.addWidget(label)
        if extra is not None:
            head_row.addWidget(extra)
        outer.addWidget(head)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(10, 10, 10, 10)
        self.body.setSpacing(9)
        outer.addLayout(self.body)


def field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("FieldLabel")
    return label


def button(text: str, kind: str = "", hold: bool = False) -> QPushButton:
    btn = QPushButton(text)
    if kind:
        btn.setObjectName(kind)
    if hold:  # автоповтор при удержании — как на физическом пульте
        btn.setAutoRepeat(True)
        btn.setAutoRepeatDelay(400)
        btn.setAutoRepeatInterval(260)
    return btn


class Segmented(QWidget):
    """Группа взаимоисключающих кнопок; отдаёт значение выбранной."""

    activated = Signal(str)

    def __init__(self, items: list[tuple[str, str]]) -> None:
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}

        for value, text in items:
            btn = QPushButton(text)
            btn.setObjectName("Seg")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, v=value: self.activated.emit(v))
            self._group.addButton(btn)
            row.addWidget(btn)
            self._buttons[value] = btn

    def set_value(self, value: str) -> None:
        for key, btn in self._buttons.items():
            btn.setChecked(key == value)

    def set_enabled(self, on: bool) -> None:
        for btn in self._buttons.values():
            btn.setEnabled(on)

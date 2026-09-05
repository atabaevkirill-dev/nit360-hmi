"""NIT-360 HMI — интерфейс пульта на PySide6.

Запуск:            python pyside/main.py
Снимок экрана:     python pyside/main.py --screenshot out.png [--demo]
Версия сборки:     python pyside/main.py --version
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from link import SerialLink
from protocol import DEMO_PATH, format_hours, is_out_of_warranty
from resources import resource_path
from widgets import Led, Panel, Segmented, button, field_label

APP_VERSION = "1.0.0"


def app_icon() -> QIcon:
    """Иконка окна и панели задач; в сборке лежит рядом с распакованными ресурсами."""
    path = resource_path("assets/icon.png")
    return QIcon(str(path)) if path.exists() else QIcon()


def mono_font() -> QFont:
    """Моноширинный шрифт журнала: своё имя на каждой ОС, иначе Qt ищет несуществующее
    семейство и тратит сотни миллисекунд на перебор алиасов."""
    font = QFont()
    font.setStyleHint(QFont.StyleHint.Monospace)
    if sys.platform == "darwin":
        font.setFamilies(["SF Mono", "Menlo", "Monaco"])
    elif sys.platform == "win32":
        font.setFamilies(["Consolas", "Cascadia Mono", "Courier New"])
    else:
        font.setFamilies(["DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono"])
    font.setPointSize(10)
    return font


class MainWindow(QMainWindow):
    # запросы к рабочему потоку
    request_ports = Signal()
    request_open = Signal(str, int, int)
    request_close = Signal()
    request_send = Signal(str)
    request_send_param = Signal(str, int)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NIT-360 HMI | Тепловизор")
        self.setWindowIcon(app_icon())
        self.resize(1380, 880)
        self.setMinimumSize(1120, 740)

        self._connected = False
        self._command_widgets: list = []
        self._segments: list = []
        self._counters = {"tx": 0, "rx": 0, "err": 0}
        self._state = {
            "polarity": "positive",
            "dde": False,
            "digitalZoom": "x1",
            "crosshair": False,
            "fov": "large",
            "filter": False,
            "irMode": "auto",
            "language": "RU",
            "runtimeHours": 0,
        }

        self._build_ui()
        self._start_link()
        self._apply_state()
        self._set_controls_enabled(False)

        clock = QTimer(self)
        clock.timeout.connect(self._tick_clock)
        clock.start(1000)
        self._tick_clock()

    # ── сборка интерфейса ────────────────────────────────────
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_topbar())

        grid = QWidget()
        columns = QHBoxLayout(grid)
        columns.setContentsMargins(10, 10, 10, 10)
        columns.setSpacing(10)
        columns.addWidget(self._build_left(), 26)
        columns.addWidget(self._build_middle(), 44)
        columns.addWidget(self._build_right(), 30)
        outer.addWidget(grid, 1)

        outer.addWidget(self._build_statusbar())

    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("Topbar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 8, 16, 8)
        row.setSpacing(18)

        brand = QVBoxLayout()
        brand.setSpacing(1)
        mark_row = QHBoxLayout()
        mark_row.setSpacing(0)
        nit = QLabel("NIT")
        nit.setObjectName("BrandMark")
        num = QLabel("360")
        num.setObjectName("BrandAccent")
        mark_row.addWidget(nit)
        mark_row.addWidget(num)
        mark_row.addStretch()
        brand.addLayout(mark_row)
        sub = QLabel("ТЕПЛОВИЗОР · RS-422 · 640×512 · 3.7–4.8 мкм")
        sub.setObjectName("BrandSub")
        brand.addWidget(sub)
        row.addLayout(brand)
        row.addStretch()

        self.led_link = Led()
        self.led_traffic = Led()
        row.addLayout(self._led_group(self.led_link, "RS-422"))
        row.addLayout(self._led_group(self.led_traffic, "ОБМЕН"))

        self.lbl_runtime = self._readout(row, "НАРАБОТКА", "—")
        self.lbl_clock = self._readout(row, "ДАТА И ВРЕМЯ", "--.--.---- --:--:--")
        return bar

    @staticmethod
    def _led_group(led: Led, text: str) -> QHBoxLayout:
        box = QHBoxLayout()
        box.setSpacing(6)
        box.addWidget(led)
        label = QLabel(text)
        label.setObjectName("LedLabel")
        box.addWidget(label)
        return box

    @staticmethod
    def _readout(row: QHBoxLayout, key: str, value: str) -> QLabel:
        box = QVBoxLayout()
        box.setSpacing(0)
        k = QLabel(key)
        k.setObjectName("ReadoutKey")
        k.setAlignment(Qt.AlignmentFlag.AlignRight)
        v = QLabel(value)
        v.setObjectName("ReadoutValue")
        v.setAlignment(Qt.AlignmentFlag.AlignRight)
        v.setTextFormat(Qt.TextFormat.RichText)
        box.addWidget(k)
        box.addWidget(v)
        row.addLayout(box)
        return v

    def _build_left(self) -> QWidget:
        col = QWidget()
        box = QVBoxLayout(col)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)

        self.chip = QLabel("НЕТ СВЯЗИ")
        self.chip.setObjectName("Chip")
        conn = Panel("ПОДКЛЮЧЕНИЕ", self.chip)

        self.cmb_port = QComboBox()
        port_row = QHBoxLayout()
        port_row.setSpacing(6)
        port_row.addWidget(self.cmb_port, 1)
        self.btn_refresh = button("ОБН", "Ghost")
        self.btn_refresh.setFixedWidth(46)
        self.btn_refresh.clicked.connect(self.request_ports)
        port_row.addWidget(self.btn_refresh)

        self.cmb_baud = QComboBox()
        self.cmb_baud.addItems(["2400", "9600", "19200"])
        self.cmb_baud.setCurrentText("9600")

        self.spin_id = QSpinBox()
        self.spin_id.setRange(0, 255)
        self.spin_id.setValue(9)

        self.btn_connect = button("ПОДКЛЮЧИТЬ", "Primary")
        self.btn_connect.clicked.connect(self._on_connect)
        self.btn_disconnect = button("ОТКЛЮЧИТЬ", "Danger")
        self.btn_disconnect.clicked.connect(self.request_close)
        self.btn_disconnect.setEnabled(False)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addWidget(self.btn_connect)
        btn_row.addWidget(self.btn_disconnect)

        self.lbl_hint = QLabel("Формат кадра 8N1, 7 байт, XOR-контроль.")
        self.lbl_hint.setObjectName("Hint")
        self.lbl_hint.setWordWrap(True)

        for widget in (field_label("Порт"),):
            conn.body.addWidget(widget)
        conn.body.addLayout(port_row)
        conn.body.addWidget(field_label("Скорость, бод"))
        conn.body.addWidget(self.cmb_baud)
        conn.body.addWidget(field_label("ID устройства"))
        conn.body.addWidget(self.spin_id)
        conn.body.addLayout(btn_row)
        conn.body.addWidget(self.lbl_hint)
        box.addWidget(conn)

        state = Panel("СОСТОЯНИЕ")
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.state_labels: dict[str, QLabel] = {}
        rows = [
            ("polarity", "Полярность"), ("digitalZoom", "Цифр. зум"),
            ("dde", "DDE"), ("crosshair", "Перекрестие"),
            ("filter", "Фильтр"), ("fov", "Поле зрения"),
            ("irMode", "Режим ИК"), ("language", "Язык OSD"),
            ("runtimeHours", "Наработка"),
        ]
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        for index, (key, title) in enumerate(rows):
            cell = QVBoxLayout()
            cell.setSpacing(1)
            k = QLabel(title)
            k.setObjectName("StateKey")
            v = QLabel("—")
            v.setObjectName("StateValue")
            cell.addWidget(k)
            cell.addWidget(v)
            # наработка длиннее прочих — растягиваем на обе колонки,
            # иначе её текст перекашивает всю сетку
            if key == "runtimeHours":
                grid.addLayout(cell, index // 2, 0, 1, 2)
            else:
                grid.addLayout(cell, index // 2, index % 2)
            self.state_labels[key] = v
        state.body.addLayout(grid)
        box.addWidget(state)

        service = Panel("СЕРВИС")
        srv_row = QHBoxLayout()
        srv_row.setSpacing(8)
        self.btn_check = button("ПРОВЕРКА СВЯЗИ")
        self.btn_check.clicked.connect(lambda: self.request_send.emit("check_comm"))
        self.btn_runtime = button("НАРАБОТКА")
        self.btn_runtime.clicked.connect(lambda: self.request_send.emit("get_runtime"))
        srv_row.addWidget(self.btn_check)
        srv_row.addWidget(self.btn_runtime)
        service.body.addLayout(srv_row)
        service.body.addWidget(field_label("Язык меню прибора"))
        self.seg_lang = Segmented([("RU", "РУС"), ("EN", "ENG")])
        self.seg_lang.activated.connect(self._on_language)
        service.body.addWidget(self.seg_lang)
        box.addWidget(service)
        box.addStretch()
        return col

    def _build_middle(self) -> QWidget:
        col = QWidget()
        box = QVBoxLayout(col)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)

        focus = Panel("ФОКУС И ЗУМ")
        focus.body.addWidget(field_label("Фокусировка"))
        focus.body.addLayout(self._cmd_row([
            ("◄ ДАЛЕКО", "focus_far", "", True),
            ("АВТО", "focus_auto", "Primary", False),
            ("БЛИЗКО ►", "focus_near", "", True),
        ]))
        focus.body.addWidget(field_label("Оптический зум · 18–360 мм"))
        focus.body.addLayout(self._cmd_row([
            ("− ШИРОКО", "zoom_wide", "", True),
            ("+ ТЕЛЕ", "zoom_tele", "", True),
        ]))
        focus.body.addWidget(field_label("Цифровой зум"))
        self.seg_dzoom = self._segment([("x1", "×1"), ("x2", "×2"), ("x4", "×4")],
                                       {"x1": "dzoom_x1", "x2": "dzoom_x2", "x4": "dzoom_x4"})
        focus.body.addWidget(self.seg_dzoom)
        box.addWidget(focus)

        image = Panel("ИЗОБРАЖЕНИЕ")
        image.body.addWidget(field_label("Полярность"))
        self.seg_polarity = self._segment(
            [("positive", "БЕЛОЕ-ГОРЯЧЕЕ"), ("negative", "ЧЁРНОЕ-ГОРЯЧЕЕ")],
            {"positive": "polarity_pos", "negative": "polarity_neg"})
        image.body.addWidget(self.seg_polarity)
        image.body.addWidget(field_label("Режим яркости и контраста"))
        self.seg_ir = self._segment([("auto", "АВТО"), ("manual", "РУЧНОЙ")],
                                    {"auto": "ir_auto", "manual": "ir_manual"})
        image.body.addWidget(self.seg_ir)

        pair = QHBoxLayout()
        pair.setSpacing(12)
        for title, minus, plus in (
            ("Яркость", "brightness_minus", "brightness_plus"),
            ("Контраст", "contrast_minus", "contrast_plus"),
        ):
            cell = QVBoxLayout()
            cell.setSpacing(6)
            cell.addWidget(field_label(title))
            cell.addLayout(self._cmd_row([("−", minus, "", True), ("+", plus, "", True)]))
            pair.addLayout(cell)
        image.body.addLayout(pair)
        image.body.addWidget(field_label("Время интеграции"))
        image.body.addLayout(self._cmd_row([
            ("− УМЕНЬШИТЬ", "int_time_minus", "", True),
            ("+ УВЕЛИЧИТЬ", "int_time_plus", "", True),
        ]))
        box.addWidget(image)

        funcs = Panel("ФУНКЦИИ")
        toggles = QGridLayout()
        toggles.setHorizontalSpacing(12)
        toggles.setVerticalSpacing(8)
        self.seg_dde = self._segment([("on", "ВКЛ"), ("off", "ВЫКЛ")],
                                     {"on": "dde_on", "off": "dde_off"})
        self.seg_crosshair = self._segment([("on", "ВКЛ"), ("off", "ВЫКЛ")],
                                           {"on": "crosshair_on", "off": "crosshair_off"})
        self.seg_filter = self._segment([("on", "ВКЛ"), ("off", "ВЫКЛ")],
                                        {"on": "filter_on", "off": "filter_off"})
        self.seg_fov = self._segment([("large", "БОЛЬШОЕ"), ("small", "МАЛОЕ")],
                                     {"large": "fov_large", "small": "fov_small"})
        for index, (title, seg) in enumerate([
            ("DDE", self.seg_dde), ("Перекрестие", self.seg_crosshair),
            ("Фильтр", self.seg_filter), ("Поле зрения", self.seg_fov),
        ]):
            cell = QVBoxLayout()
            cell.setSpacing(5)
            cell.addWidget(field_label(title))
            cell.addWidget(seg)
            toggles.addLayout(cell, index // 2, index % 2)
        funcs.body.addLayout(toggles)
        self.btn_nuc = button("НУК · КОРРЕКЦИЯ НЕОДНОРОДНОСТИ", "Warn")
        self.btn_nuc.clicked.connect(lambda: self.request_send.emit("nuc"))
        funcs.body.addWidget(self.btn_nuc)
        box.addWidget(funcs)
        box.addStretch()
        return col

    def _build_right(self) -> QWidget:
        col = QWidget()
        box = QVBoxLayout(col)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)

        actions = QWidget()
        act_row = QHBoxLayout(actions)
        act_row.setContentsMargins(0, 0, 0, 0)
        act_row.setSpacing(6)
        btn_clear = button("ОЧИСТИТЬ", "Ghost")
        btn_clear.setFixedWidth(84)
        btn_clear.clicked.connect(self._clear_log)
        act_row.addWidget(btn_clear)

        log_panel = Panel("ЖУРНАЛ ОБМЕНА", actions)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("Log")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(500)
        self.log_view.setFont(mono_font())
        self.log_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        log_panel.body.addWidget(self.log_view)

        self.lbl_counters = QLabel("TX 0    RX 0    ОШИБОК 0")
        self.lbl_counters.setObjectName("Hint")
        log_panel.body.addWidget(self.lbl_counters)
        box.addWidget(log_panel, 1)
        return col

    def _build_statusbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("Statusbar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 5, 14, 5)
        self.lbl_status = QLabel("Готово")
        self.lbl_status.setObjectName("StatusMsg")
        right = QLabel(f"NIT-360 HMI Control Panel v{APP_VERSION} · протокол 7 байт · RS-422 Full Duplex")
        right.setObjectName("StatusRight")
        row.addWidget(self.lbl_status)
        row.addStretch()
        row.addWidget(right)
        return bar

    # ── помощники сборки ─────────────────────────────────────
    def _cmd_row(self, items: list[tuple[str, str, str, bool]]) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        for text, cmd, kind, hold in items:
            btn = button(text, kind, hold=hold)
            btn.clicked.connect(lambda _=False, c=cmd: self.request_send.emit(c))
            row.addWidget(btn)
            self._command_widgets.append(btn)
        return row

    def _segment(self, items: list[tuple[str, str]], mapping: dict[str, str]) -> Segmented:
        seg = Segmented(items)
        seg.activated.connect(lambda value, m=mapping: self.request_send.emit(m[value]))
        self._segments.append(seg)
        return seg

    # ── поток связи ──────────────────────────────────────────
    def _start_link(self) -> None:
        self._thread = QThread(self)
        self._link = SerialLink()
        self._link.moveToThread(self._thread)

        self.request_ports.connect(self._link.list_ports)
        self.request_open.connect(self._link.open_port)
        self.request_close.connect(self._link.close_port)
        self.request_send.connect(self._link.send)
        self.request_send_param.connect(self._link.send_with_param)

        self._link.ports_listed.connect(self._on_ports)
        self._link.connection_changed.connect(self._on_connection)
        self._link.log.connect(self._on_log)
        self._link.command_done.connect(self._on_command_done)
        self._link.runtime_read.connect(self._on_runtime)

        self._thread.start()
        self.request_ports.emit()

    def closeEvent(self, event) -> None:  # noqa: N802 — имя из Qt
        self.request_close.emit()
        self._thread.quit()
        self._thread.wait(1500)
        super().closeEvent(event)

    # ── реакции ──────────────────────────────────────────────
    def _on_connect(self) -> None:
        path = self.cmb_port.currentData() or self.cmb_port.currentText()
        if not path:
            self._set_status("Выберите порт", "error")
            return
        self._set_status(f"Подключение к {path}…")
        self.request_open.emit(path, int(self.cmb_baud.currentText()), self.spin_id.value())

    def _on_language(self, lang: str) -> None:
        from protocol import LANGUAGE_MAP

        self.request_send_param.emit("set_language", LANGUAGE_MAP[lang])
        self._state["language"] = lang
        self._apply_state()

    def _on_ports(self, ports: list[dict]) -> None:
        self.cmb_port.clear()
        for port in ports:
            title = f"{port['path']} — {port['description']}" if port["description"] else port["path"]
            self.cmb_port.addItem(title, port["path"])
        self.cmb_port.addItem("ДЕМО — эмулятор прибора", DEMO_PATH)
        self._set_status(
            f"Найдено портов: {len(ports)}" if ports
            else "COM-порты не найдены — доступен демо-режим"
        )

    def _on_connection(self, status: dict) -> None:
        was_connected = self._connected
        self._connected = bool(status["connected"])
        demo = bool(status["demo"])

        self.led_link.set_state("warn" if demo else ("on" if self._connected else "off"))
        self.chip.setText("ДЕМО-РЕЖИМ" if demo else ("НА СВЯЗИ" if self._connected else "НЕТ СВЯЗИ"))
        self.chip.setProperty("state", "demo" if demo else ("on" if self._connected else ""))
        self.chip.style().unpolish(self.chip)
        self.chip.style().polish(self.chip)

        self.btn_connect.setEnabled(not self._connected)
        self.btn_disconnect.setEnabled(self._connected)
        for widget in (self.cmb_port, self.cmb_baud, self.spin_id, self.btn_refresh):
            widget.setEnabled(not self._connected)
        self._set_controls_enabled(self._connected)

        if self._connected and not was_connected:
            QTimer.singleShot(150, lambda: self.request_send.emit("get_runtime"))

        if self._connected:
            self.lbl_hint.setText(
                "Встроенный эмулятор прибора. Команды не уходят в порт."
                if demo else f"{status['port']} · {status['baud']} бод · 8N1 · ID {status['id']}"
            )
        else:
            self.lbl_hint.setText("Формат кадра 8N1, 7 байт, XOR-контроль.")

    def _on_log(self, kind: str, data: str) -> None:
        if kind in ("tx", "rx"):
            self._counters[kind] += 1
        elif kind == "error":
            self._counters["err"] += 1
        self.lbl_counters.setText(
            f"TX {self._counters['tx']}    RX {self._counters['rx']}    ОШИБОК {self._counters['err']}"
        )

        tag = {"tx": "TX ", "rx": "RX ", "info": "···", "error": "ERR"}.get(kind, "···")
        stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_view.appendPlainText(f"{stamp}  {tag}  {data}")
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

        self.led_traffic.set_state("error" if kind == "error" else "on")
        QTimer.singleShot(150, lambda: self.led_traffic.set_state("off"))

    def _on_command_done(self, cmd_id: str, success: bool, status: int, error: str) -> None:
        from protocol import COMMANDS

        name = COMMANDS.get(cmd_id, (0, cmd_id))[1]
        if success:
            self._set_status(f"{name} — выполнено", "ok")
            self._update_state(cmd_id)
        else:
            self._set_status(error or f"{name}: отклонено (статус {status})", "error")

    def _on_runtime(self, hours: int) -> None:
        self._state["runtimeHours"] = hours
        self._apply_state()
        if is_out_of_warranty(hours):
            self._set_status(
                f"Наработка прибора: {format_hours(hours)} — ВНЕ ГАРАНТИИ", "error"
            )
        else:
            self._set_status(f"Наработка прибора: {format_hours(hours)}", "ok")

    # ── состояние прибора ────────────────────────────────────
    def _update_state(self, cmd_id: str) -> None:
        mapping = {
            "polarity_pos": ("polarity", "positive"), "polarity_neg": ("polarity", "negative"),
            "dde_on": ("dde", True), "dde_off": ("dde", False),
            "dzoom_x1": ("digitalZoom", "x1"), "dzoom_x2": ("digitalZoom", "x2"),
            "dzoom_x4": ("digitalZoom", "x4"),
            "crosshair_on": ("crosshair", True), "crosshair_off": ("crosshair", False),
            "fov_large": ("fov", "large"), "fov_small": ("fov", "small"),
            "filter_on": ("filter", True), "filter_off": ("filter", False),
            "ir_manual": ("irMode", "manual"), "ir_auto": ("irMode", "auto"),
        }
        if cmd_id in mapping:
            key, value = mapping[cmd_id]
            self._state[key] = value
            self._apply_state()

    def _apply_state(self) -> None:
        s = self._state
        text = {
            "polarity": {"positive": "БЕЛОЕ-ГОРЯЧЕЕ", "negative": "ЧЁРНОЕ-ГОРЯЧЕЕ"},
            "irMode": {"auto": "АВТО", "manual": "РУЧНОЙ"},
            "fov": {"large": "БОЛЬШОЕ", "small": "МАЛОЕ"},
        }
        self.state_labels["polarity"].setText(text["polarity"][s["polarity"]])
        self.state_labels["digitalZoom"].setText("×" + s["digitalZoom"].removeprefix("x"))
        self.state_labels["dde"].setText("ВКЛ" if s["dde"] else "ВЫКЛ")
        self.state_labels["crosshair"].setText("ВКЛ" if s["crosshair"] else "ВЫКЛ")
        self.state_labels["filter"].setText("ВКЛ" if s["filter"] else "ВЫКЛ")
        self.state_labels["fov"].setText(text["fov"][s["fov"]])
        self.state_labels["irMode"].setText(text["irMode"][s["irMode"]])
        self.state_labels["language"].setText("ENG" if s["language"] == "EN" else "РУС")
        self._apply_runtime(s["runtimeHours"])

        self.seg_polarity.set_value(s["polarity"])
        self.seg_ir.set_value(s["irMode"])
        self.seg_fov.set_value(s["fov"])
        self.seg_dzoom.set_value(s["digitalZoom"])
        self.seg_dde.set_value("on" if s["dde"] else "off")
        self.seg_crosshair.set_value("on" if s["crosshair"] else "off")
        self.seg_filter.set_value("on" if s["filter"] else "off")
        self.seg_lang.set_value(s["language"])

    def _apply_runtime(self, hours: int) -> None:
        """Свыше ресурса наработка подсвечивается красным и помечается негарантийной."""
        alarm = is_out_of_warranty(hours)
        compact = f"{hours:,}".replace(",", " ") + " ч" if hours else "—"

        text = format_hours(hours) if hours else "—"
        if alarm:
            text += " · ВНЕ ГАРАНТИИ"

        label = self.state_labels["runtimeHours"]
        label.setText(text)
        label.setStyleSheet("color: #e5484d;" if alarm else "")
        self.lbl_runtime.setText(compact)
        self.lbl_runtime.setStyleSheet("color: #e5484d;" if alarm else "")
        self.lbl_runtime.setToolTip(
            f"Наработка превысила ресурс {10000:,} ч — прибор вне гарантии".replace(",", " ")
            if alarm else ""
        )

    def _set_controls_enabled(self, on: bool) -> None:
        for widget in self._command_widgets:
            widget.setEnabled(on)
        for seg in self._segments:
            seg.set_enabled(on)
        for widget in (self.btn_check, self.btn_runtime, self.btn_nuc):
            widget.setEnabled(on)
        self.seg_lang.set_enabled(on)

    def _set_status(self, text: str, kind: str = "") -> None:
        color = {"ok": "#23c8a0", "error": "#e5484d"}.get(kind, "#c8d6e5")
        self.lbl_status.setStyleSheet(f"color: {color};")
        self.lbl_status.setText(text)

    def _clear_log(self) -> None:
        self.log_view.clear()
        self._counters = {"tx": 0, "rx": 0, "err": 0}
        self.lbl_counters.setText("TX 0    RX 0    ОШИБОК 0")

    def _tick_clock(self) -> None:
        now = datetime.now()
        # дата приглушена, время — основной акцент; обе части в одном поле шапки
        self.lbl_clock.setText(
            f'<span style="color:#6b8199">{now:%d.%m.%Y}</span>&nbsp;&nbsp;{now:%H:%M:%S}'
        )


def main() -> int:
    args = sys.argv[1:]
    if "--version" in args:
        print(f"NIT-360 HMI {APP_VERSION}")
        return 0

    app = QApplication(sys.argv)
    app.setApplicationName("NIT-360 HMI")
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(app_icon())
    app.setStyleSheet(resource_path("style.qss").read_text(encoding="utf-8"))

    window = MainWindow()
    window.show()

    if "--demo" in args:
        QTimer.singleShot(300, lambda: window.request_open.emit(DEMO_PATH, 9600, 9))
        QTimer.singleShot(700, lambda: window.request_send.emit("get_runtime"))
        QTimer.singleShot(900, lambda: window.request_send.emit("polarity_neg"))
        QTimer.singleShot(1100, lambda: window.request_send.emit("dzoom_x2"))

    if "--screenshot" in args:
        path = args[args.index("--screenshot") + 1]

        def shoot() -> None:
            window.grab().save(path)
            app.quit()

        QTimer.singleShot(1800, shoot)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

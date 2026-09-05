"""Связь с прибором в отдельном потоке: одна команда за раз, ответ ждём синхронно."""
from __future__ import annotations

import time

import serial
from serial.tools import list_ports
from PySide6.QtCore import QObject, Signal, Slot

from protocol import (
    COMMANDS,
    DEFAULT_ID,
    DEMO_PATH,
    FRAME_LEN,
    DemoDevice,
    FrameParser,
    build_command,
    parse_response,
    to_hex,
)

RESPONSE_TIMEOUT = 2.0


class SerialLink(QObject):
    """Живёт в рабочем потоке. Все слоты вызываются через очередь сигналов,
    поэтому команды сериализуются сами собой — гонок запрос/ответ нет."""

    log = Signal(str, str)                    # тип (tx/rx/info/error), текст
    connection_changed = Signal(dict)         # {connected, port, baud, id, demo}
    command_done = Signal(str, bool, int, str)  # cmd_id, успех, статус, ошибка
    runtime_read = Signal(int)
    ports_listed = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self._port: serial.Serial | None = None
        self._demo: DemoDevice | None = None
        self._parser = FrameParser()
        self._device_id = DEFAULT_ID
        self._baud = 9600

    # ── состояние ────────────────────────────────────────────
    @property
    def is_open(self) -> bool:
        return self._demo is not None or (self._port is not None and self._port.is_open)

    def _status(self) -> dict:
        return {
            "connected": self.is_open,
            "port": DEMO_PATH if self._demo else (self._port.port if self._port else None),
            "baud": self._baud,
            "id": self._device_id,
            "demo": self._demo is not None,
        }

    # ── слоты ────────────────────────────────────────────────
    @Slot()
    def list_ports(self) -> None:
        try:
            found = [
                {"path": p.device, "description": "" if p.description in (None, "", "n/a") else p.description}
                for p in list_ports.comports()
            ]
        except Exception as err:  # noqa: BLE001 — показываем пользователю любую причину
            found = []
            self.log.emit("error", f"Не удалось получить список портов: {err}")
        self.ports_listed.emit(found)

    @Slot(str, int, int)
    def open_port(self, path: str, baud: int, device_id: int) -> None:
        self.close_port(silent=True)
        self._baud = baud
        self._device_id = device_id
        if path == DEMO_PATH:
            self._demo = DemoDevice()
            self.log.emit("info", "Демо-режим: команды обрабатывает встроенный эмулятор")
            self.connection_changed.emit(self._status())
            return
        try:
            self._port = serial.Serial(
                port=path,
                baudrate=baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=RESPONSE_TIMEOUT,
                write_timeout=RESPONSE_TIMEOUT,
            )
            self.log.emit("info", f"Подключено: {path} @ {baud} бод, ID: {device_id}")
        except Exception as err:  # noqa: BLE001
            self._port = None
            self.log.emit("error", f"Не удалось открыть порт: {err}")
        self.connection_changed.emit(self._status())

    @Slot()
    def close_port(self, silent: bool = False) -> None:
        self._parser.reset()
        self._demo = None
        if self._port is not None:
            try:
                self._port.close()
            except Exception:  # noqa: BLE001 — порт мог исчезнуть вместе с адаптером
                pass
            self._port = None
        if not silent:
            self.log.emit("info", "Порт закрыт")
            self.connection_changed.emit(self._status())

    @Slot(str)
    def send(self, cmd_id: str) -> None:
        entry = COMMANDS.get(cmd_id)
        if entry is None:
            self.command_done.emit(cmd_id, False, -1, f"Неизвестная команда: {cmd_id}")
            return
        self._exchange(cmd_id, entry[0], 0x00)

    @Slot(str, int)
    def send_with_param(self, cmd_id: str, param: int) -> None:
        entry = COMMANDS.get(cmd_id)
        if entry is None:
            self.command_done.emit(cmd_id, False, -1, f"Неизвестная команда: {cmd_id}")
            return
        self._exchange(cmd_id, entry[0], param)

    # ── обмен ────────────────────────────────────────────────
    def _exchange(self, cmd_id: str, code: int, param: int) -> None:
        if not self.is_open:
            self.command_done.emit(cmd_id, False, -1, "Порт не подключён")
            return

        frame = build_command(self._device_id, code, param)
        self.log.emit("tx", to_hex(frame))

        reply = self._demo_exchange(frame) if self._demo else self._serial_exchange(frame, code)
        if reply is None:
            self.command_done.emit(cmd_id, False, -1, f"Таймаут ответа ({RESPONSE_TIMEOUT:.0f} с)")
            self.log.emit("error", f"{COMMANDS[cmd_id][1]}: нет ответа")
            return

        self.log.emit("rx", to_hex(reply))
        result = parse_response(reply, code)
        self.command_done.emit(cmd_id, result.success, result.status, result.error)
        if cmd_id == "get_runtime" and result.success:
            self.runtime_read.emit(result.runtime_hours)
        elif not result.success and result.error:
            self.log.emit("error", f"{COMMANDS[cmd_id][1]}: {result.error}")

    def _demo_exchange(self, frame: bytes) -> bytes:
        time.sleep(0.05)
        return self._demo.respond(frame)

    def _serial_exchange(self, frame: bytes, code: int) -> bytes | None:
        assert self._port is not None
        try:
            self._port.reset_input_buffer()
            self._parser.reset()
            self._port.write(frame)
        except Exception as err:  # noqa: BLE001
            self.log.emit("error", f"Ошибка записи в порт: {err}")
            return None

        deadline = time.monotonic() + RESPONSE_TIMEOUT
        while time.monotonic() < deadline:
            try:
                chunk = self._port.read(FRAME_LEN)
            except Exception as err:  # noqa: BLE001
                self.log.emit("error", f"Ошибка чтения из порта: {err}")
                return None
            if not chunk:
                continue
            for reply in self._parser.push(chunk):
                if reply[3] == code:  # ответ на нашу команду, а не «хвост» прошлой
                    return reply
        return None

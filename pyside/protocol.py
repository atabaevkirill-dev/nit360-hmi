"""Протокол NIT-360: кадр 7 байт FF <id> 00 <code> <param> 00 <XOR байтов 1..5>."""
from __future__ import annotations

import os
from dataclasses import dataclass

STATUS_SUCCESS = 0x01
DEFAULT_ID = 0x09
FRAME_LEN = 7
DEMO_PATH = "DEMO"

BAUD_MAP = {2400: 0x00, 9600: 0x01, 19200: 0x02}
LANGUAGE_MAP = {"EN": 0x00, "RU": 0x01}

COMMANDS: dict[str, tuple[int, str]] = {
    "focus_far": (0x01, "Фокус Далеко"),
    "focus_near": (0x08, "Фокус Близко"),
    "focus_auto": (0x2B, "Автофокус"),
    "zoom_tele": (0x20, "Зум +"),
    "zoom_wide": (0x40, "Зум -"),
    "polarity_pos": (0x7F, "Полярность +"),
    "polarity_neg": (0x81, "Полярность -"),
    "int_time_plus": (0x83, "Время интеграции +"),
    "int_time_minus": (0x85, "Время интеграции -"),
    "dde_on": (0x87, "DDE ВКЛ"),
    "dde_off": (0x89, "DDE ВЫКЛ"),
    "dzoom_x1": (0x8B, "Цифр. зум x1"),
    "dzoom_x2": (0x8D, "Цифр. зум x2"),
    "dzoom_x4": (0x8F, "Цифр. зум x4"),
    "nuc": (0x91, "НУК"),
    "brightness_plus": (0x93, "Яркость +"),
    "brightness_minus": (0x95, "Яркость -"),
    "contrast_plus": (0x97, "Контраст +"),
    "contrast_minus": (0x99, "Контраст -"),
    "ir_manual": (0xA7, "Ручная ИК"),
    "ir_auto": (0xA9, "Авто ИК"),
    "crosshair_on": (0x9B, "Перекрестие ВКЛ"),
    "crosshair_off": (0x9D, "Перекрестие ВЫКЛ"),
    "set_id": (0x9F, "Установить ID"),
    "set_baud": (0xA1, "Установить скорость"),
    "fov_large": (0xA3, "Большое ПЗ"),
    "fov_small": (0xA5, "Малое ПЗ"),
    "filter_on": (0xAD, "Фильтр ВКЛ"),
    "filter_off": (0xAF, "Фильтр ВЫКЛ"),
    "check_comm": (0xB1, "Проверка связи"),
    "set_language": (0xB3, "Смена языка"),
    "get_runtime": (0xB5, "Наработка часов"),
}

CODE_TO_NAME = {code: name for code, name in COMMANDS.values()}


def checksum(frame: bytes) -> int:
    cs = 0
    for i in range(1, 6):
        cs ^= frame[i]
    return cs


def build_command(device_id: int, code: int, param: int = 0x00) -> bytes:
    frame = bytearray(FRAME_LEN)
    frame[0] = 0xFF
    frame[1] = device_id & 0xFF
    frame[2] = 0x00
    frame[3] = code & 0xFF
    frame[4] = param & 0xFF
    frame[5] = 0x00
    frame[6] = checksum(frame)
    return bytes(frame)


# Команды, у которых байты 4 и 5 несут не статус, а 16-битное значение
# (старший байт первым). Для них статус не проверяется: у наработки
# 1274 ч старший байт равен 0x04, и проверка «0x01 = успех» ложно
# отбраковала бы совершенно нормальный ответ.
DATA_REPLY_CODES = frozenset({COMMANDS["get_runtime"][0]})


@dataclass(frozen=True)
class Response:
    success: bool
    status: int
    t1: int = 0
    t2: int = 0
    error: str = ""
    value: int | None = None

    @property
    def runtime_hours(self) -> int:
        """16-битное значение ответа; для 0xB5 — часы наработки."""
        return ((self.t1 << 8) | self.t2) & 0xFFFF


def parse_response(data: bytes, code: int | None = None) -> Response:
    """Разбирает кадр ответа. `code` — опкод запроса: по нему решается,
    статус в байте 4 или старший байт данных."""
    if len(data) != FRAME_LEN:
        return Response(False, -1, error="Длина кадра")
    if data[0] != 0xFF:
        return Response(False, -2, error="Заголовок кадра")
    if data[6] != checksum(data):
        return Response(False, -3, error="Контрольная сумма")

    value = ((data[4] << 8) | data[5]) & 0xFFFF
    if code is not None and code in DATA_REPLY_CODES:
        return Response(True, data[4], t1=data[4], t2=data[5], value=value)
    return Response(data[4] == STATUS_SUCCESS, data[4], t1=data[4], t2=data[5], value=value)


# Ресурс, после которого прибор считается вышедшим из гарантии.
WARRANTY_HOURS = 10_000


def is_out_of_warranty(hours: int) -> bool:
    return hours > WARRANTY_HOURS


def format_hours(hours: int) -> str:
    """1274 → «1 274 ч · 53 сут»."""
    grouped = f"{hours:,}".replace(",", " ")
    days = hours // 24
    return f"{grouped} ч · {days} сут" if days else f"{grouped} ч"


def to_hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


class FrameParser:
    """Собирает поток байтов в кадры по 7, ресинхронизируясь по 0xFF."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def push(self, chunk: bytes) -> list[bytes]:
        self._buf.extend(chunk)
        frames: list[bytes] = []
        while True:
            start = self._buf.find(0xFF)
            if start == -1:
                self._buf.clear()
                return frames
            if start:
                del self._buf[:start]
            if len(self._buf) < FRAME_LEN:
                return frames
            frames.append(bytes(self._buf[:FRAME_LEN]))
            del self._buf[:FRAME_LEN]

    def reset(self) -> None:
        self._buf.clear()


class DemoDevice:
    """Эмулятор прибора: отвечает валидными кадрами без железа."""

    def __init__(self) -> None:
        # NIT360_DEMO_HOURS позволяет проверить пороги, например негарантийную наработку
        self.runtime = int(os.environ.get("NIT360_DEMO_HOURS", 1274)) & 0xFFFF

    def respond(self, frame: bytes) -> bytes:
        out = bytearray(FRAME_LEN)
        out[0] = 0xFF
        out[1] = frame[1]
        out[2] = 0x00
        out[3] = frame[3]
        if frame[3] == COMMANDS["get_runtime"][0]:
            out[4] = (self.runtime >> 8) & 0xFF
            out[5] = self.runtime & 0xFF
        else:
            out[4] = STATUS_SUCCESS
            out[5] = frame[4]
        out[6] = checksum(out)
        return bytes(out)

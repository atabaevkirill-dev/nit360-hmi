"""Тесты кодека протокола. Запуск: .venv/bin/python pyside/test_protocol.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from protocol import (
    WARRANTY_HOURS,
    DemoDevice,
    FrameParser,
    build_command,
    checksum,
    format_hours,
    is_out_of_warranty,
    parse_response,
)


def test_frame_shape():
    f = build_command(0x09, 0x91)
    assert len(f) == 7 and f[0] == 0xFF


def test_checksum_is_xor_of_1_5():
    f = build_command(0x09, 0x91, 0x02)
    assert f[6] == checksum(f) == f[1] ^ f[2] ^ f[3] ^ f[4] ^ f[5]


def test_valid_response():
    assert parse_response(bytes([0xFF, 9, 0, 0x91, 0x01, 0, 0x99])).success


def test_bad_checksum():
    assert parse_response(bytes([0xFF, 9, 0, 0x91, 1, 0, 0x00])).status == -3


def test_short_frame():
    assert parse_response(bytes([0xFF, 9, 0])).status == -1


def test_runtime_pair():
    demo = DemoDevice()
    reply = demo.respond(build_command(0x09, 0xB5))
    assert parse_response(reply).runtime_hours == 1274


def test_runtime_reply_is_not_judged_by_status_byte():
    # 1274 ч = 0x04FA: старший байт 0x04, а не 0x01 — ответ обязан считаться успешным
    reply = DemoDevice().respond(build_command(0x09, 0xB5))
    parsed = parse_response(reply, 0xB5)
    assert parsed.success and parsed.value == 1274


def test_status_byte_still_checked_for_normal_commands():
    frame = bytearray([0xFF, 9, 0, 0x91, 0x04, 0, 0])
    frame[6] = checksum(frame)
    assert parse_response(bytes(frame), 0x91).success is False


def test_runtime_edges():
    for hours in (0, 1, 255, 256, 1274, 0xFFFF):
        frame = bytearray([0xFF, 9, 0, 0xB5, (hours >> 8) & 0xFF, hours & 0xFF, 0])
        frame[6] = checksum(frame)
        assert parse_response(bytes(frame), 0xB5).value == hours


def test_format_hours():
    assert format_hours(1274) == "1 274 ч · 53 сут"
    assert format_hours(12) == "12 ч"


def test_warranty_threshold():
    assert WARRANTY_HOURS == 10_000
    assert is_out_of_warranty(10_000) is False   # ровно ресурс — ещё в гарантии
    assert is_out_of_warranty(10_001) is True
    assert is_out_of_warranty(0) is False


def test_parser_resyncs_and_splits():
    f = build_command(0x09, 0x01)
    parser = FrameParser()
    frames = []
    for byte in bytes([0x00, 0x11]) + f + f:
        frames.extend(parser.push(bytes([byte])))
    assert len(frames) == 2 and frames[0] == f


if __name__ == "__main__":
    failed = 0
    tests = {k: v for k, v in sorted(globals().items()) if k.startswith("test_")}
    for name, fn in tests.items():
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as err:
            failed += 1
            print(f"  ✗ {name}: {err}")
    print(f"\n{len(tests) - failed} из {len(tests)} пройдено")
    sys.exit(1 if failed else 0)

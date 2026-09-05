from __future__ import annotations

import struct
from pathlib import Path

import pytest

from app.csgo_demo_format import (
    DemoFormatError,
    classify_demo_magic,
    read_hl2demo_header,
    require_csgo_demo,
)


def _hl2demo_bytes(*, map_name: str = "de_dust2", ticks: int = 640, time_sec: float = 10.0) -> bytes:
    buf = bytearray(1068)
    buf[0:8] = b"HL2DEMO\0"
    struct.pack_into("<i", buf, 8, 4)
    struct.pack_into("<i", buf, 12, 137)
    buf[536:536 + len(map_name)] = map_name.encode("ascii")
    struct.pack_into("<f", buf, 1056, time_sec)
    struct.pack_into("<i", buf, 1060, ticks)
    return bytes(buf)


def test_classify_magic():
    assert classify_demo_magic(b"HL2DEMO\0") == "hl2demo"
    assert classify_demo_magic(b"PBDEMS2\0") == "pbdems2"
    assert classify_demo_magic(b"XXXX") == "unknown"


def test_require_csgo_demo_accepts_hl2demo(tmp_path: Path):
    path = tmp_path / "match.dem"
    path.write_bytes(_hl2demo_bytes())
    assert require_csgo_demo(path).startswith(b"HL2DEMO")


def test_require_csgo_demo_rejects_cs2(tmp_path: Path):
    path = tmp_path / "cs2.dem"
    path.write_bytes(b"PBDEMS2\0" + b"\x00" * 32)
    with pytest.raises(DemoFormatError) as error:
        require_csgo_demo(path)
    assert error.value.code == "DEMO_CS2_NOT_SUPPORTED"


def test_read_hl2demo_header_tick_rate(tmp_path: Path):
    path = tmp_path / "faceit.dem"
    path.write_bytes(_hl2demo_bytes(map_name="de_mirage", ticks=1280, time_sec=10.0))
    header = read_hl2demo_header(path)
    assert header["map_name"] == "de_mirage"
    assert header["tick_rate"] == pytest.approx(128.0)

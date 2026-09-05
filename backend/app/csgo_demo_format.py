"""Source 1 CS:GO demo magic-byte gate."""

from __future__ import annotations

from pathlib import Path

HL2DEMO_MAGIC = b"HL2DEMO"
PBDEMS2_MAGIC = b"PBDEMS2"
_HEADER_BYTES = 8

# HL2DEMO on-disk header (Source 1):
#   8  magic
#   4  demo protocol
#   4  network protocol
# 260  server name
# 260  client name
# 260  map name
# 260  game directory
#   4  playback time (float32)
#   4  playback ticks (int32)
#   4  playback frames (int32)
#   4  signon length (int32)
_HL2_SERVER_OFF = 16
_HL2_CLIENT_OFF = 276
_HL2_MAP_OFF = 536
_HL2_GAME_OFF = 796
_HL2_TIME_OFF = 1056
_HL2_TICKS_OFF = 1060
_HL2_MIN_HEADER = 1068


class DemoFormatError(ValueError):
    """Raised when a .dem file is not a supported CS:GO Source 1 demo."""

    def __init__(self, message: str, *, code: str = "DEMO_INSPECTION_FAILED"):
        super().__init__(message)
        self.code = code


def read_demo_magic(path: str | Path) -> bytes:
    target = Path(path)
    with target.open("rb") as handle:
        return handle.read(_HEADER_BYTES)


def classify_demo_magic(magic: bytes) -> str:
    if magic.startswith(HL2DEMO_MAGIC):
        return "hl2demo"
    if magic.startswith(PBDEMS2_MAGIC):
        return "pbdems2"
    return "unknown"


def require_csgo_demo(path: str | Path) -> bytes:
    """Return the 8-byte magic, or raise DemoFormatError."""
    target = Path(path)
    if target.suffix.lower() != ".dem":
        raise DemoFormatError(f"not a .dem file: {target}", code="DEMO_INVALID_EXTENSION")
    try:
        magic = read_demo_magic(target)
    except OSError as exc:
        raise DemoFormatError(f"Demo file not found: {target}") from exc
    kind = classify_demo_magic(magic)
    if kind == "hl2demo":
        return magic
    if kind == "pbdems2":
        raise DemoFormatError(
            "This is a CS2 (PBDEMS2) demo. CSGO Insight Agent only parses Source 1 CS:GO demos.",
            code="DEMO_CS2_NOT_SUPPORTED",
        )
    raise DemoFormatError(
        f"{target} is not a CS:GO HL2DEMO file",
        code="DEMO_INSPECTION_FAILED",
    )


def _cstring(buf: bytes, offset: int, length: int = 260) -> str:
    chunk = buf[offset : offset + length]
    return chunk.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()


def read_hl2demo_header(path: str | Path) -> dict[str, object]:
    """Parse the fixed Source 1 demo header without a full netmessage scan."""
    require_csgo_demo(path)
    raw = Path(path).read_bytes()[:_HL2_MIN_HEADER]
    if len(raw) < _HL2_MIN_HEADER:
        raise DemoFormatError("HL2DEMO header is truncated", code="DEMO_INSPECTION_FAILED")
    import struct

    demo_protocol = struct.unpack_from("<i", raw, 8)[0]
    network_protocol = struct.unpack_from("<i", raw, 12)[0]
    playback_time = float(struct.unpack_from("<f", raw, _HL2_TIME_OFF)[0])
    playback_ticks = int(struct.unpack_from("<i", raw, _HL2_TICKS_OFF)[0])
    tick_rate = 64.0
    if playback_time > 0.05 and playback_ticks > 0:
        tick_rate = float(playback_ticks) / playback_time
        if tick_rate < 16 or tick_rate > 256:
            tick_rate = 64.0
    return {
        "headername": "HL2DEMO",
        "demo_protocol": demo_protocol,
        "network_protocol": network_protocol,
        "server_name": _cstring(raw, _HL2_SERVER_OFF),
        "client_name": _cstring(raw, _HL2_CLIENT_OFF),
        "map_name": _cstring(raw, _HL2_MAP_OFF),
        "game_directory": _cstring(raw, _HL2_GAME_OFF),
        "playback_time": playback_time,
        "playback_ticks": playback_ticks,
        "tick_rate": tick_rate,
        "tickrate": tick_rate,
    }

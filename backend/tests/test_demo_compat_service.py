import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app import demo_compat_service as service
from app.csgo_demo_format import DemoFormatError
from app.demo_playback_compat import PATCH_ID, PATCH_REVISION, PlaybackDemoReport


def _clean_report() -> PlaybackDemoReport:
    return PlaybackDemoReport(
        schema_version=1,
        outcome="clean",
        patch_id=PATCH_ID,
        patch_revision=PATCH_REVISION,
        removed_messages=0,
        changed_frames=0,
        first_tick=None,
        last_tick=None,
        max_per_frame=0,
        remaining_selected_messages=0,
    )


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _frame(command: int, tick: int, payload: bytes, *, declared_size=None) -> bytes:
    size = len(payload) if declared_size is None else declared_size
    return _varint(command) + _varint(tick) + _varint(size) + payload


def _hl2demo_bytes(*, map_name: str = "de_dust2", ticks: int = 640, time_sec: float = 10.0) -> bytes:
    """Minimal fixed Source 1 demo header accepted by require_csgo_demo()."""
    import struct

    buf = bytearray(1068)
    buf[0:8] = b"HL2DEMO\\0"
    struct.pack_into("<i", buf, 8, 4)
    struct.pack_into("<i", buf, 12, 137)
    buf[536:536 + len(map_name)] = map_name.encode("ascii")
    struct.pack_into("<f", buf, 1056, time_sec)
    struct.pack_into("<i", buf, 1060, ticks)
    return bytes(buf)


def test_ensure_demo_compatible_persists_and_reuses_fingerprint(monkeypatch, tmp_path: Path):
    source = tmp_path / "match.dem"
    source.write_bytes(_hl2demo_bytes())
    cache = tmp_path / "compat-cache.json"
    calls: list[Path] = []

    def fake_repair(path, **_kwargs):
        calls.append(Path(path))
        return _clean_report()

    monkeypatch.setattr(service, "_cache_path", lambda: cache)
    monkeypatch.setattr(service, "repair_demo_in_place", fake_repair)

    first = service.ensure_demo_compatible(source)
    second = service.ensure_demo_compatible(source)

    assert first.cached is False
    assert second.cached is True
    assert calls == [source.resolve()]
    assert cache.is_file()


def test_ensure_demo_compatible_invalidates_when_file_changes(monkeypatch, tmp_path: Path):
    source = tmp_path / "match.dem"
    source.write_bytes(_hl2demo_bytes(map_name="de_first"))
    calls = 0

    def fake_repair(_path, **_kwargs):
        nonlocal calls
        calls += 1
        return _clean_report()

    monkeypatch.setattr(service, "_cache_path", lambda: tmp_path / "cache.json")
    monkeypatch.setattr(service, "repair_demo_in_place", fake_repair)

    service.ensure_demo_compatible(source)
    source.write_bytes(_hl2demo_bytes(map_name="de_second"))
    result = service.ensure_demo_compatible(source)

    assert result.cached is False
    assert calls == 2


def test_terminal_recovery_is_default_but_can_be_strict(monkeypatch, tmp_path: Path):
    source = tmp_path / "match.dem"
    source.write_bytes(_hl2demo_bytes())
    ensure_options: list[bool] = []

    def fake_repair(_path, *, allow_truncated_packet_tail=False):
        ensure_options.append(allow_truncated_packet_tail)
        return _clean_report()

    monkeypatch.setattr(service, "_cache_path", lambda: tmp_path / "cache.json")
    monkeypatch.setattr(service, "repair_demo_in_place", fake_repair)

    service.ensure_demo_compatible(source)

    source.write_bytes(_hl2demo_bytes(map_name="de_changed"))
    service.ensure_demo_compatible(source, allow_truncated_packet_tail=False)

    assert ensure_options == [True, False]


def test_source2_demo_is_rejected_before_any_compatibility_rewrite(
    monkeypatch,
    tmp_path: Path,
):
    """CS:GO-only product: PBDEMS2 never enters the compatibility rewriter."""

    source = tmp_path / "cs2.dem"
    source_bytes = b"PBDEMS2\\x00" + b"\\x00" * 32
    source.write_bytes(source_bytes)
    monkeypatch.setattr(service, "_cache_path", lambda: tmp_path / "cache.json")

    def unexpected_repair(*_args, **_kwargs):
        raise AssertionError("Source 2 demos must not reach the compatibility rewriter")

    monkeypatch.setattr(service, "repair_demo_in_place", unexpected_repair)

    with pytest.raises(DemoFormatError) as error:
        service.ensure_demo_compatible(source)

    assert error.value.code == "DEMO_NOT_CSGO"
    assert source.read_bytes() == source_bytes


def test_compatible_baseline_repairs_once_and_never_mutates_original(
    monkeypatch,
    tmp_path: Path,
):
    source = tmp_path / "library" / "match.dem"
    source.parent.mkdir()
    source_bytes = _hl2demo_bytes(map_name="de_original")
    source.write_bytes(source_bytes)
    cache_dir = tmp_path / "cache"
    calls: list[Path] = []

    def fake_repair(path, **_kwargs):
        candidate = Path(path)
        calls.append(candidate)
        candidate.write_bytes(candidate.read_bytes() + b"-COMPAT")
        return _clean_report()

    monkeypatch.setattr(service, "_cache_path", lambda: tmp_path / "compat-cache.json")
    monkeypatch.setattr(service, "repair_demo_in_place", fake_repair)

    first = service.ensure_compatible_baseline(source, cache_dir)
    second = service.ensure_compatible_baseline(source, cache_dir)

    assert first == second
    assert first.parent == cache_dir.resolve()
    assert first.read_bytes() == source_bytes + b"-COMPAT"
    assert source.read_bytes() == source_bytes
    assert len(calls) == 1
    assert first.with_suffix(".json").is_file()


def test_compatible_baseline_invalidates_when_original_changes(monkeypatch, tmp_path: Path):
    source = tmp_path / "match.dem"
    source.write_bytes(_hl2demo_bytes(map_name="de_first"))
    cache_dir = tmp_path / "cache"
    calls = 0

    def fake_repair(path, **_kwargs):
        nonlocal calls
        calls += 1
        candidate = Path(path)
        candidate.write_bytes(candidate.read_bytes() + b"-COMPAT")
        return _clean_report()

    monkeypatch.setattr(service, "_cache_path", lambda: tmp_path / "compat-cache.json")
    monkeypatch.setattr(service, "repair_demo_in_place", fake_repair)

    first = service.ensure_compatible_baseline(source, cache_dir)
    source.write_bytes(_hl2demo_bytes(map_name="de_second"))
    second = service.ensure_compatible_baseline(source, cache_dir)

    assert first != second
    assert first.read_bytes() == _hl2demo_bytes(map_name="de_first") + b"-COMPAT"
    assert second.read_bytes() == _hl2demo_bytes(map_name="de_second") + b"-COMPAT"
    assert calls == 2


def test_compatible_baseline_failure_publishes_nothing(monkeypatch, tmp_path: Path):
    source = tmp_path / "match.dem"
    source_bytes = _hl2demo_bytes(map_name="de_original")
    source.write_bytes(source_bytes)
    cache_dir = tmp_path / "cache"

    def broken_repair(_path, **_kwargs):
        raise RuntimeError("repair failed")

    monkeypatch.setattr(service, "_cache_path", lambda: tmp_path / "compat-cache.json")
    monkeypatch.setattr(service, "repair_demo_in_place", broken_repair)

    try:
        service.ensure_compatible_baseline(source, cache_dir)
    except RuntimeError as exc:
        assert str(exc) == "repair failed"
    else:
        raise AssertionError("baseline construction must fail closed")

    assert source.read_bytes() == source_bytes
    assert not list(cache_dir.glob(".skin-compat-v*.dem"))
    assert not list(cache_dir.glob(".skin-compat-build-*.dem"))

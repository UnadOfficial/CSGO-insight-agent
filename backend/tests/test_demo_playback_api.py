"""HTTP boundary for the CS:GO-only direct playback path."""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.demo_playback import api as playback_api
from app.csgo_demo_format import DemoFormatError


def _hl2demo_bytes(payload: bytes = b"") -> bytes:
    return b"HL2DEMO" + payload


def _configured_csgo(tmp_path: Path):
    game_root = tmp_path / "Counter-Strike Global Offensive"
    csgo = game_root / "csgo.exe"
    csgo.parent.mkdir(parents=True)
    csgo.write_bytes(b"exe")
    (game_root / "csgo").mkdir()
    return SimpleNamespace(csgo_path=str(csgo))


def _demo(tmp_path: Path) -> Path:
    demo = tmp_path / "match.dem"
    demo.write_bytes(_hl2demo_bytes(b"demo"))
    return demo


def test_alias_roster_resolves_library_and_path(monkeypatch, tmp_path):
    from unittest.mock import AsyncMock

    path = tmp_path / "sample.dem"
    players = [{"steamid64": "76561199032006224", "name": "Etagekax", "team_number": 2}]
    monkeypatch.setattr(playback_api.demo_db, "get_demo_by_id", AsyncMock(return_value={"id": 7}))
    monkeypatch.setattr(playback_api, "_library_working_demo_path", AsyncMock(return_value=path))
    monkeypatch.setattr(playback_api, "resolve_uploaded_demo_path_async", AsyncMock(return_value=path))

    def roster(value):
        assert value == path
        return players

    monkeypatch.setattr(playback_api, "player_alias_roster", roster)
    for body in [playback_api.AliasRosterBody(id=7), playback_api.AliasRosterBody(path="sample.dem")]:
        assert asyncio.run(playback_api.demo_alias_roster(body)) == {"players": players}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(playback_api.demo_alias_roster(playback_api.AliasRosterBody()))
    assert exc.value.status_code == 422


def test_aliases_are_forwarded(monkeypatch, tmp_path):
    cfg = _configured_csgo(tmp_path)
    demo = _demo(tmp_path)
    captured = {}
    monkeypatch.setattr(playback_api, "load_config", lambda: cfg)
    monkeypatch.setattr(playback_api, "ensure_csgo_path", lambda value: value)

    def launch(path, config, options):
        captured.update(path=path, config=config, options=options)
        return {"ok": True}

    monkeypatch.setattr(playback_api.demo_playback_service, "launch", launch)
    playback_api.launch_csgo_play_demo(
        demo,
        playback_api.DemoPlaybackOptionsBody(player_aliases={"76561199032006224": "京介"}),
    )

    assert captured["path"] == demo
    assert captured["config"] is cfg
    assert captured["options"] == playback_api.DemoPlaybackOptions(
        player_aliases={"76561199032006224": "京介"}
    )


def test_missing_csgo_path_returns_stable_code(monkeypatch, tmp_path):
    demo = _demo(tmp_path)
    monkeypatch.setattr(playback_api, "load_config", lambda: SimpleNamespace(csgo_path=""))
    monkeypatch.setattr(playback_api, "ensure_csgo_path", lambda value: value)

    with pytest.raises(HTTPException) as exc_info:
        playback_api.launch_csgo_play_demo(demo, playback_api.DemoPlaybackOptionsBody())

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == {"code": "DEMO_PLAYBACK_CSGO_PATH_MISSING"}


def test_source2_demo_is_rejected_with_dedicated_code(monkeypatch, tmp_path):
    cfg = _configured_csgo(tmp_path)
    demo = tmp_path / "match.dem"
    demo.write_bytes(b"PBDEMS2" + b"\x00" * 32)
    monkeypatch.setattr(playback_api, "load_config", lambda: cfg)
    monkeypatch.setattr(playback_api, "ensure_csgo_path", lambda value: value)

    with pytest.raises(HTTPException) as exc_info:
        playback_api.launch_csgo_play_demo(demo, playback_api.DemoPlaybackOptionsBody())

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == {"code": "DEMO_NOT_CSGO"}


def test_launch_maps_running_process_to_stable_409(monkeypatch, tmp_path: Path):
    cfg = _configured_csgo(tmp_path)
    demo = _demo(tmp_path)
    monkeypatch.setattr(playback_api, "load_config", lambda: cfg)
    monkeypatch.setattr(playback_api, "ensure_csgo_path", lambda value: value)
    monkeypatch.setattr(
        playback_api.demo_playback_service,
        "launch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            playback_api.DemoPlaybackCSGORunningError()
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        playback_api.launch_csgo_play_demo(demo, playback_api.DemoPlaybackOptionsBody())

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {"code": "DEMO_PLAYBACK_CSGO_RUNNING"}


def test_busy_playback_maps_to_stable_409(monkeypatch, tmp_path: Path):
    cfg = _configured_csgo(tmp_path)
    demo = _demo(tmp_path)
    monkeypatch.setattr(playback_api, "load_config", lambda: cfg)
    monkeypatch.setattr(playback_api, "ensure_csgo_path", lambda value: value)
    monkeypatch.setattr(
        playback_api.demo_playback_service,
        "launch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(playback_api.DemoPlaybackBusyError()),
    )

    with pytest.raises(HTTPException) as exc_info:
        playback_api.launch_csgo_play_demo(demo, playback_api.DemoPlaybackOptionsBody())

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {"code": "DEMO_PLAYBACK_BUSY"}


@pytest.mark.parametrize(
    "retired_field",
    [
        "recording_skybox",
        "recording_map_material",
        "recording_weather_effect",
        "skybox_id",
        "map_material_id",
        "weather_effect_id",
        "pov_hud",
    ],
)
def test_retired_source2_options_are_rejected(monkeypatch, tmp_path: Path, retired_field):
    """A stale client must get a hard error instead of silent no-op behaviour."""
    cfg = _configured_csgo(tmp_path)
    demo = _demo(tmp_path)
    monkeypatch.setattr(playback_api, "load_config", lambda: cfg)
    monkeypatch.setattr(playback_api, "ensure_csgo_path", lambda value: value)
    monkeypatch.setattr(playback_api.demo_playback_service, "launch", pytest.fail)

    body = playback_api.DemoPlaybackOptionsBody(**{retired_field: "chroma_green"})
    with pytest.raises(HTTPException) as exc_info:
        playback_api.launch_csgo_play_demo(demo, body)

    assert exc_info.value.status_code == 410
    assert exc_info.value.detail["code"] == "CSGO_UNSUPPORTED_FEATURE"


def test_preflight_delegates_to_playback_service(monkeypatch, tmp_path: Path):
    cfg = _configured_csgo(tmp_path)
    monkeypatch.setattr(playback_api, "load_config", lambda: cfg)
    monkeypatch.setattr(playback_api, "ensure_csgo_path", lambda value: value)
    monkeypatch.setattr(
        playback_api.demo_playback_service,
        "preflight",
        lambda config: {
            "ok": False,
            "csgo_path_configured": True,
            "csgo_running": config is cfg,
            "playback_active": False,
            "warnings": [],
        },
    )

    result = asyncio.run(playback_api.demo_playback_preflight())

    assert result == {
        "ok": False,
        "csgo_path_configured": True,
        "csgo_running": True,
        "playback_active": False,
        "warnings": [],
    }


def test_playback_status_returns_measured_session_report(monkeypatch):
    monkeypatch.setattr(
        playback_api.demo_playback_service,
        "session_status",
        lambda session_id: {
            "found": True,
            "session_id": session_id,
            "state": "completed",
            "player_config_restore": {"verified": True},
        },
    )

    result = asyncio.run(playback_api.demo_playback_status("session-123"))

    assert result == {
        "found": True,
        "session_id": "session-123",
        "state": "completed",
        "player_config_restore": {"verified": True},
    }


def test_demo_format_error_is_mapped_to_its_code(monkeypatch, tmp_path: Path):
    cfg = _configured_csgo(tmp_path)
    demo = _demo(tmp_path)
    monkeypatch.setattr(playback_api, "load_config", lambda: cfg)
    monkeypatch.setattr(playback_api, "ensure_csgo_path", lambda value: value)

    def reject(_path):
        raise DemoFormatError("truncated", code="DEMO_INSPECTION_FAILED")

    monkeypatch.setattr(playback_api, "require_csgo_demo", reject)

    with pytest.raises(HTTPException) as exc_info:
        playback_api.launch_csgo_play_demo(demo, playback_api.DemoPlaybackOptionsBody())

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == {"code": "DEMO_INSPECTION_FAILED"}

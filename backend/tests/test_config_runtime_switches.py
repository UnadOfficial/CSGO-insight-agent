"""PUT /api/config 的 CS:GO-only 运行时开关回归测试。"""

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.api import config as config_api
from app.env_utils import AppConfig, OBSConfig


def _round_trip(monkeypatch, payload: config_api.ConfigPayload, *, initial: AppConfig | None = None) -> AppConfig:
    cfg = initial or AppConfig(obs=OBSConfig())
    saved: list[AppConfig] = []
    monkeypatch.setattr(config_api, "load_config", lambda: cfg)
    monkeypatch.setattr(config_api, "save_config", lambda updated: saved.append(updated))
    asyncio.run(config_api.update_config(payload))
    assert saved, "update_config 必须落盘"
    return saved[-1]


def test_source2_visual_fields_no_longer_exist():
    """The CS:GO-only config model must not carry Source 2 recording state."""
    cfg = AppConfig(obs=OBSConfig())

    for retired in (
        "recording_skybox",
        "recording_map_material",
        "recording_weather_effect",
    ):
        assert not hasattr(cfg, retired), f"{retired} must be removed from AppConfig"


def test_retired_source2_config_fields_are_rejected():
    """A stale client sending a retired field must be rejected loudly."""
    for retired in (
        "recording_skybox",
        "recording_map_material",
        "recording_weather_effect",
    ):
        with pytest.raises(ValidationError):
            config_api.ConfigPayload(**{retired: "cartoon3"})


def test_csgo_path_survives_the_round_trip(monkeypatch):
    payload = config_api.ConfigPayload(csgo_path=r"C:\Steam\csgo.exe")

    assert _round_trip(monkeypatch, payload).csgo_path == r"C:\Steam\csgo.exe"


def test_csgo_extra_launch_args_mark_user_configuration(monkeypatch):
    payload = config_api.ConfigPayload(csgo_extra_launch_args="-novid -console")

    cfg = _round_trip(monkeypatch, payload)

    assert cfg.csgo_extra_launch_args == "-novid -console"
    assert cfg.csgo_extra_launch_args_user_configured is True


def test_hlae_path_survives_the_round_trip(monkeypatch):
    payload = config_api.ConfigPayload(hlae_path=r"C:\HLAE\HLAE.exe")

    assert _round_trip(monkeypatch, payload).hlae_path == r"C:\HLAE\HLAE.exe"


def test_hlae_mirv_pov_flag_survives_the_round_trip(monkeypatch):
    payload = config_api.ConfigPayload(hlae_mirv_pov_enabled=True)

    assert _round_trip(monkeypatch, payload).hlae_mirv_pov_enabled is True


def test_detect_csgo_endpoint_persists_the_detected_path(monkeypatch, tmp_path: Path):
    game_root = tmp_path / "Counter-Strike Global Offensive"
    csgo = game_root / "csgo.exe"
    csgo.parent.mkdir(parents=True)
    csgo.write_bytes(b"exe")
    (game_root / "csgo" / "cfg").mkdir(parents=True)

    saved: list[AppConfig] = []
    monkeypatch.setattr(config_api, "detect_csgo_path", lambda: str(csgo))
    monkeypatch.setattr(config_api, "load_config", lambda: AppConfig(obs=OBSConfig()))
    monkeypatch.setattr(config_api, "save_config", lambda updated: saved.append(updated))

    assert config_api.detect_csgo_save() == {"csgo_path": str(csgo)}
    assert saved[-1].csgo_path == str(csgo)


def test_detect_csgo_endpoint_reports_a_missing_install(monkeypatch):
    monkeypatch.setattr(config_api, "detect_csgo_path", lambda: None)

    with pytest.raises(HTTPException) as exc_info:
        config_api.detect_csgo_save()

    assert exc_info.value.status_code == 404
    assert "csgo.exe" in str(exc_info.value.detail)

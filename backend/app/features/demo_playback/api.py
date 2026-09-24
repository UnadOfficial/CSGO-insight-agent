"""HTTP boundary for managed CS:GO demo playback."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from ...api_errors import error_detail
from ...databases import demo_db
from ...demo_cache import ensure_row_cached
from ...demo_paths import UPLOAD_DIR, resolve_working_demo_path
from ...demo_playback_service import (
    DemoPlaybackBusyError,
    DemoPlaybackCSGORunningError,
    DemoPlaybackOptions,
    demo_playback_service,
)
from ...csgo_demo_format import DemoFormatError, require_csgo_demo
from ...env_utils import ensure_csgo_path, load_config
from ...player_aliases import PlayerAliases, PlayerAliasError, player_alias_roster
from ...runtime_session import runtime_session_dependency

logger = logging.getLogger(__name__)
router = APIRouter(tags=["demo-playback"])


class DemoPlaybackOptionsBody(BaseModel):
    model_config = ConfigDict(extra="allow")

    player_aliases: PlayerAliases = Field(default_factory=dict)


class DemoPlayByPathBody(DemoPlaybackOptionsBody):
    path: str = Field(..., min_length=1)


async def resolve_uploaded_demo_path_async(path: str) -> Path:
    return await resolve_working_demo_path(path, demo_db=demo_db, upload_dir=UPLOAD_DIR)


async def _library_working_demo_path(row: dict[str, Any]) -> Path:
    try:
        return await ensure_row_cached(demo_db, row)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


def launch_csgo_play_demo(
    demo_path: Path,
    options: Optional[DemoPlaybackOptionsBody] = None,
) -> dict[str, Any]:
    cfg = ensure_csgo_path(load_config())
    if not cfg.csgo_path or not Path(cfg.csgo_path).is_file():
        raise HTTPException(400, error_detail("DEMO_PLAYBACK_CSGO_PATH_MISSING"))
    if not demo_path.is_file():
        raise HTTPException(422, error_detail("DEMO_PLAYBACK_DEMO_NOT_FOUND", path=str(demo_path)))
    try:
        require_csgo_demo(demo_path)
    except DemoFormatError as exc:
        raise HTTPException(422, error_detail(exc.code)) from exc

    body = options or DemoPlaybackOptionsBody()
    unsupported = set(getattr(body, "model_extra", {}) or {}) & {
        "recording_skybox",
        "recording_map_material",
        "recording_weather_effect",
        "skybox_id",
        "map_material_id",
        "weather_effect_id",
        "pov_hud",
        "pov_hud_enabled",
        "recording_hud_enabled",
        "experimental_pov_enabled",
        "input_hud_enabled",
        "input_hud_display_mode",
        "input_audio_enabled",
        "combat_stats_hud_enabled",
        "pov_radar_mode",
        "pov_teamcounter_numeric",
    }
    if unsupported:
        raise HTTPException(
            410,
            error_detail(
                "CSGO_UNSUPPORTED_FEATURE",
                feature="source2_pov_hud",
            ),
        )
    try:
        return demo_playback_service.launch(
            demo_path,
            cfg,
            DemoPlaybackOptions(player_aliases=dict(body.player_aliases)),
        )
    except PlayerAliasError as exc:
        raise HTTPException(422, str(exc)) from exc
    except DemoFormatError as exc:
        raise HTTPException(422, error_detail(exc.code)) from exc
    except DemoPlaybackCSGORunningError as exc:
        raise HTTPException(409, error_detail("DEMO_PLAYBACK_CSGO_RUNNING")) from exc
    except DemoPlaybackBusyError as exc:
        raise HTTPException(409, error_detail("DEMO_PLAYBACK_BUSY")) from exc
    except FileNotFoundError as exc:
        raise HTTPException(400, error_detail("DEMO_PLAYBACK_CSGO_PATH_MISSING")) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to launch CS:GO for direct playback")
        raise HTTPException(500, error_detail("DEMO_PLAYBACK_LAUNCH_FAILED", err=str(exc))) from exc


@router.get("/api/demo/playback/preflight")
async def demo_playback_preflight():
    cfg = ensure_csgo_path(load_config())
    result = await asyncio.to_thread(demo_playback_service.preflight, cfg)
    return result


class AliasRosterBody(BaseModel):
    id: Optional[int] = Field(default=None, gt=0)
    path: Optional[str] = Field(default=None, max_length=32768)


@router.post("/api/demo/alias-roster")
async def demo_alias_roster(body: AliasRosterBody):
    if body.id is not None:
        row = await demo_db.get_demo_by_id(body.id)
        if not row:
            raise HTTPException(404, "Demo not found")
        path = await _library_working_demo_path(row)
    elif body.path:
        path = await resolve_uploaded_demo_path_async(body.path)
    else:
        raise HTTPException(422, "Missing demo path or id")
    try:
        return {"players": await asyncio.to_thread(player_alias_roster, path)}
    except PlayerAliasError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/api/demo/playback/status")
async def demo_playback_status(session_id: str = Query(..., min_length=1, max_length=128)):
    return await asyncio.to_thread(demo_playback_service.session_status, session_id)


@router.post("/api/demo/play")
async def play_demo_by_path(
    body: DemoPlayByPathBody,
    _runtime_session: None = Depends(runtime_session_dependency),
):
    demo_path = await resolve_uploaded_demo_path_async(body.path)
    return await asyncio.to_thread(launch_csgo_play_demo, demo_path, body)


@router.post("/api/demos/{demo_id}/play")
async def play_demo_by_id(
    demo_id: int,
    body: Optional[DemoPlaybackOptionsBody] = Body(default=None),
    _runtime_session: None = Depends(runtime_session_dependency),
):
    """Launch a library demo through the same managed CS:GO playback path."""
    row = await demo_db.get_demo_by_id(demo_id)
    if not row:
        raise HTTPException(404, f"Demo not found: {demo_id}")
    demo_path = await _library_working_demo_path(row)
    if not demo_path.is_file():
        raise HTTPException(422, "Demo file is missing from disk and cannot be played")
    return await asyncio.to_thread(launch_csgo_play_demo, demo_path, body)

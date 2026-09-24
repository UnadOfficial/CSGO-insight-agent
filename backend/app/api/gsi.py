"""Game State Integration readiness routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body

from ..gsi_ready import gsi_status, notify_gsi_payload

router = APIRouter(prefix="/api/gsi", tags=["gsi"])


@router.post("/csgo")
async def csgo_gsi(payload: Optional[dict] = Body(default=None)):
    """Canonical CS:GO GSI sink used by the recording startup gate."""
    ready = notify_gsi_payload(payload or {})
    return {"ok": True, "ready": ready}


@router.get("/status")
def csgo_gsi_status():
    return gsi_status()

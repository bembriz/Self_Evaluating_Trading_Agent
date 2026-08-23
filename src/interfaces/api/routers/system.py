"""Endpoints de estado del sistema (PRD §54)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from application.ports.repositories import SystemStateRepository
from interfaces.api.deps import get_repository, get_settings
from settings import Settings

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/state")
async def system_state(
    repo: Annotated[SystemStateRepository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Estado del sistema: prioriza lo persistido en DB y cae a settings."""
    db_state = await repo.get("system") or {}
    return {
        "trading_mode": db_state.get("trading_mode", settings.trading_mode),
        "live_trading_enabled": db_state.get("live_trading_enabled", settings.live_trading_enabled),
        "version": settings.app_version,
    }

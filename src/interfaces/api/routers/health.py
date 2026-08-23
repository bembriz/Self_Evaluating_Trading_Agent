"""Endpoints de liveness/readiness (PRD §54)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from application.ports.repositories import SystemStateRepository
from interfaces.api.deps import get_repository

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: el proceso está vivo. No depende de la base de datos."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(
    repo: Annotated[SystemStateRepository, Depends(get_repository)],
) -> JSONResponse:
    """Readiness: comprueba conectividad con PostgreSQL (SELECT 1)."""
    if await repo.ping():
        return JSONResponse({"status": "ready"})
    return JSONResponse(status_code=503, content={"status": "not_ready"})

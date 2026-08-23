"""Dependencias de FastAPI: sesión, repositorio y settings inyectados."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

from fastapi import Request

from application.ports.repositories import SystemStateRepository
from infrastructure.database.repositories import SqlAlchemySystemStateRepository
from settings import Settings


async def get_repository(
    request: Request,
) -> AsyncIterator[SystemStateRepository]:
    """Yield de un repositorio respaldado por una sesión por request."""
    factory = request.app.state.session_factory
    async with factory() as session:
        yield SqlAlchemySystemStateRepository(session)


def get_settings(request: Request) -> Settings:
    """Settings cargados al arrancar la aplicación."""
    return cast(Settings, request.app.state.settings)

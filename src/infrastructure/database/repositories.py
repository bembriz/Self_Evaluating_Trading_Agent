"""Adaptadores SQLAlchemy de los puertos de persistencia."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.models import SystemState


class SqlAlchemySystemStateRepository:
    """Implementación de SystemStateRepository sobre SQLAlchemy async."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str) -> dict[str, Any] | None:
        row = await self._session.scalar(select(SystemState).where(SystemState.key == key))
        return row.value if row is not None else None

    async def set(self, key: str, value: dict[str, Any]) -> None:
        row = await self._session.scalar(select(SystemState).where(SystemState.key == key))
        if row is not None:
            row.value = value
        else:
            self._session.add(SystemState(key=key, value=value))
        await self._session.flush()

    async def ping(self) -> bool:
        try:
            await self._session.execute(text("SELECT 1"))
        except Exception:
            return False
        return True

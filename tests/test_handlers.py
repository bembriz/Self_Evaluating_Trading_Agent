"""Tests unitarios de handlers y del path de error del repositorio."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.repositories import SqlAlchemySystemStateRepository
from interfaces.api.routers.health import ready
from interfaces.api.routers.system import system_state
from settings import Settings


class _FakeRepo:
    def __init__(self, *, ping: bool, value: dict[str, Any] | None) -> None:
        self._ping = ping
        self._value = value

    async def get(self, key: str) -> dict[str, Any] | None:
        return self._value

    async def set(self, key: str, value: dict[str, Any]) -> None:
        raise NotImplementedError

    async def ping(self) -> bool:
        return self._ping


async def test_ready_200_cuando_db_ok() -> None:
    resp = await ready(_FakeRepo(ping=True, value=None))
    assert resp.status_code == 200
    assert resp.body == b'{"status":"ready"}'


async def test_ready_503_cuando_db_caida() -> None:
    resp = await ready(_FakeRepo(ping=False, value=None))
    assert resp.status_code == 503
    assert resp.body == b'{"status":"not_ready"}'


async def test_system_state_prioriza_valor_db() -> None:
    repo = _FakeRepo(
        ping=True,
        value={"trading_mode": "paper", "live_trading_enabled": True},
    )
    resp = await system_state(repo, Settings(trading_mode="backtest"))
    assert resp["trading_mode"] == "paper"
    assert resp["live_trading_enabled"] is True


async def test_repository_ping_false_en_error() -> None:
    session = AsyncMock()
    session.execute.side_effect = RuntimeError("db down")
    repo = SqlAlchemySystemStateRepository(cast(AsyncSession, session))
    assert await repo.ping() is False

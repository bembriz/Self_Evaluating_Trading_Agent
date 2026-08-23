"""Motor y sesión async de SQLAlchemy (driver psycopg3)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(url: str) -> AsyncEngine:
    """Crea un motor async; no abre conexión hasta el primer uso."""
    return create_async_engine(url, pool_pre_ping=True)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Fabrica sesiones async sin expirar atributos al hacer commit."""
    return async_sessionmaker(engine, expire_on_commit=False)

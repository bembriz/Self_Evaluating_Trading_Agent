"""Fixtures de integración: base de datos de test migrada + cliente HTTP."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from settings import Settings

TEST_HOST = os.environ.get("POSTGRES_HOST", "localhost")
TEST_PORT = int(os.environ.get("POSTGRES_PORT", "5433"))
TEST_USER = os.environ.get("POSTGRES_USER", "trading")
TEST_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "trading")
TEST_DB = "trading_agent_test"
ADMIN_DB = "trading_agent"


def make_test_settings() -> Settings:
    return Settings(
        postgres_host=TEST_HOST,
        postgres_port=TEST_PORT,
        postgres_db=TEST_DB,
        postgres_user=TEST_USER,
        postgres_password=SecretStr(TEST_PASSWORD),
    )


def _recreate_test_database() -> None:
    admin_url = f"postgresql://{TEST_USER}:{TEST_PASSWORD}@{TEST_HOST}:{TEST_PORT}/{ADMIN_DB}"
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}"')
        conn.execute(f'CREATE DATABASE "{TEST_DB}"')


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    return make_test_settings()


@pytest.fixture(scope="session")
def migrated_db(test_settings: Settings) -> Iterator[str]:
    """Recrea la DB de test y aplica un roundtrip up→down→up completo."""
    _recreate_test_database()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", test_settings.database_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield test_settings.database_url


@pytest.fixture(scope="session")
def engine(migrated_db: str) -> AsyncEngine:
    return create_async_engine(migrated_db, pool_pre_ping=True)


@pytest.fixture(scope="session")
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as s:
        yield s


@pytest.fixture(scope="session")
def client(migrated_db: str, test_settings: Settings) -> Iterator[TestClient]:
    from interfaces.api.app import create_app

    app = create_app(test_settings)
    with TestClient(app) as c:
        yield c

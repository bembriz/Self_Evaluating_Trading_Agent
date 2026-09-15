"""Fixtures de integración: base de datos de test migrada + cliente HTTP."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

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

# El CSV del dataset oficial vive bajo /datasets/ (gitignored, PRD §40) y NO está
# en CI. Los tests marcados `real_dataset` se saltan cuando falta; el manifest y
# los splits sí están versionados, así que identidad/rangos corren siempre.
REAL_DATASET_CSV = (
    Path(__file__).resolve().parents[1] / "datasets" / "BYBIT_ETHBTC_V001" / "ETHUSDT_15m.csv"
)
REAL_DATASET_AVAILABLE = REAL_DATASET_CSV.is_file()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if REAL_DATASET_AVAILABLE:
        return
    skip = pytest.mark.skip(
        reason=(
            "official frozen dataset BYBIT_ETHBTC_V001 CSV not available "
            "(gitignored under /datasets/, absent in CI)"
        )
    )
    for item in items:
        if "real_dataset" in item.keywords:
            item.add_marker(skip)


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


SYNTHETIC_DATASET_ID = "BYBIT_ETHBTC_V001"
SYNTHETIC_SYMBOL = "ETHUSDT"
SYNTHETIC_TIMEFRAME = "15m"
SYNTHETIC_ROWS = 88300


def build_synthetic_frozen_repo(root: Path, *, rows: int = SYNTHETIC_ROWS) -> Path:
    """Create a synthetic frozen dataset repo mirroring the official layout."""
    csv_path = (
        root / "datasets" / SYNTHETIC_DATASET_ID / f"{SYNTHETIC_SYMBOL}_{SYNTHETIC_TIMEFRAME}.csv"
    )
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp_ms", "open", "high", "low", "close", "volume", "turnover"])
        for index in range(rows):
            timestamp = 1_700_000_000_000 + index * 900_000
            price = 100.0 + (index % 50) * 0.1
            writer.writerow([timestamp, price, price + 1.0, price - 1.0, price, 1.0, price])

    manifest = {
        "dataset_version": SYNTHETIC_DATASET_ID,
        "files": [
            {
                "symbol": SYNTHETIC_SYMBOL,
                "timeframe": SYNTHETIC_TIMEFRAME,
                "row_count": rows,
                "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
            }
        ],
    }
    manifest_path = root / "docs" / "datasets" / f"{SYNTHETIC_DATASET_ID}.manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    split_v1 = {
        "dataset_id": SYNTHETIC_DATASET_ID,
        "dataset_manifest_sha": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "total_rows": rows,
        "split_version": 1,
    }
    split_path = root / "splits" / "v1.json"
    split_path.parent.mkdir(parents=True, exist_ok=True)
    split_path.write_text(json.dumps(split_v1), encoding="utf-8")
    return root


@pytest.fixture
def synthetic_frozen_repo(tmp_path: Path) -> Path:
    return build_synthetic_frozen_repo(tmp_path)

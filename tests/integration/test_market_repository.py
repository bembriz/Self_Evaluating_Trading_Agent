from sqlalchemy.ext.asyncio import AsyncSession

from domain.market.candle import Candle, Timeframe
from domain.market.dataset import CandleFileEntry, DatasetManifest
from infrastructure.database.repositories import (
    SqlAlchemyDatasetManifestRepository,
    SqlAlchemyMarketCandleRepository,
)


def mk(ts: int) -> Candle:
    return Candle(ts, 100.0, 110.0, 90.0, 105.0, 1.0, 100.0)


async def test_upsert_and_count(session: AsyncSession) -> None:
    repo = SqlAlchemyMarketCandleRepository(session)
    inserted = await repo.upsert("ETHUSDT", Timeframe.M15, [mk(0), mk(15 * 60_000)])
    await session.commit()
    assert inserted == 2
    assert await repo.count("ETHUSDT", Timeframe.M15) == 2
    inserted_again = await repo.upsert("ETHUSDT", Timeframe.M15, [mk(0)])
    await session.commit()
    assert inserted_again == 0
    assert await repo.count("ETHUSDT", Timeframe.M15) == 2


async def test_range(session: AsyncSession) -> None:
    repo = SqlAlchemyMarketCandleRepository(session)
    await repo.upsert("ETHUSDT", Timeframe.M15, [mk(0), mk(15 * 60_000), mk(30 * 60_000)])
    await session.commit()
    rows = await repo.range("ETHUSDT", Timeframe.M15, 15 * 60_000, 30 * 60_000)
    assert [c.timestamp_ms for c in rows] == [15 * 60_000, 30 * 60_000]


async def test_upsert_batches_large_input(session: AsyncSession) -> None:
    repo = SqlAlchemyMarketCandleRepository(session)
    step = 15 * 60_000
    candles = [mk(i * step) for i in range(2500)]
    inserted = await repo.upsert("BTCUSDT", Timeframe.M15, candles)
    await session.commit()
    assert inserted == 2500
    assert await repo.count("BTCUSDT", Timeframe.M15) == 2500


async def test_manifest_upsert_get(session: AsyncSession) -> None:
    repo = SqlAlchemyDatasetManifestRepository(session)
    m = DatasetManifest(
        dataset_version="V001",
        source="s",
        schema_version="1.0",
        symbols=("ETHUSDT",),
        timeframes=("15m",),
        downloaded_at="2026-08-23T00:00:00+00:00",
        download_command="c",
        files=(CandleFileEntry("ETHUSDT", "15m", "p", 1, "abc", 0, 0),),
    )
    await repo.upsert(m)
    await session.commit()
    assert await repo.get("V001") == m
    assert await repo.get("missing") is None

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.market.features import OrderBookFeatureSnapshot
from infrastructure.database.models import OrderBookFeatureWindow
from infrastructure.database.repositories import SqlAlchemyOrderBookFeatureRepository


def feature() -> OrderBookFeatureSnapshot:
    return OrderBookFeatureSnapshot(
        symbol="ETHUSDT",
        window_start_ms=0,
        window_end_ms=5000,
        best_bid=100.0,
        best_ask=101.0,
        spread=1.0,
        spread_pct=0.01,
        bid_depth=3.0,
        ask_depth=4.5,
        imbalance=0.4,
    )


async def test_insert_and_query(session: AsyncSession) -> None:
    repo = SqlAlchemyOrderBookFeatureRepository(session)
    await repo.insert(feature())
    await session.commit()

    rows = (await session.scalars(select(OrderBookFeatureWindow))).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.symbol == "ETHUSDT"
    assert row.best_bid == 100.0
    assert row.imbalance == 0.4
    assert row.created_at is not None

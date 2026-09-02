from sqlalchemy.ext.asyncio import AsyncSession

from application.ports.paper_trading import PaperTradeEvent
from infrastructure.database.repositories import SqlAlchemyPaperTradeEventRepository


async def test_paper_trade_event_repository_roundtrip(session: AsyncSession) -> None:
    repo = SqlAlchemyPaperTradeEventRepository(session)
    event = PaperTradeEvent(
        session_id="paper-baseline-20260901",
        strategy_version="ema-rsi-baseline-v1",
        strategy_hash="abc123",
        decision_source="baseline",
        symbol="ETHUSDT",
        timeframe="15m",
        timestamp_ms=1_725_000_000_000,
        action="BUY",
        filled=True,
        risk_reason="",
        exit_reason="",
        exec_price=2500.5,
        quantity=0.01,
        fee=0.025,
        slippage_cost=0.005,
        equity=999.97,
        kill_switch_active=False,
    )

    await repo.add(event)
    await session.commit()

    rows = await repo.list_session("paper-baseline-20260901")
    assert rows == [event]

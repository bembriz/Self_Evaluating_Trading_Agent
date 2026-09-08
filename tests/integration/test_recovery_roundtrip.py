from sqlalchemy.ext.asyncio import AsyncSession

from application.ports.paper_trading import PaperTradeEvent
from application.services.paper_runner import PaperRunner, PaperRunnerConfig
from application.services.recovery import restore_runner
from domain.market.candle import Candle, Timeframe
from infrastructure.database.repositories import (
    SqlAlchemyMarketCandleRepository,
    SqlAlchemyPaperTradeEventRepository,
    SqlAlchemySystemStateRepository,
)

TF = Timeframe.M15
TF_MS = TF.minutes * 60_000


def _candle(i: int, close: float) -> Candle:
    ts = i * TF_MS
    return Candle(ts, close - 1.0, close + 1.0, close - 2.0, close, 10.0, 1000.0)


def _uptrend(n: int, start: float = 100.0, step: float = 0.5) -> list[Candle]:
    return [_candle(i, start + i * step) for i in range(n)]


def _config(session_id: str) -> PaperRunnerConfig:
    return PaperRunnerConfig(
        trading_mode="paper",
        live_trading_enabled=False,
        symbols=("ETHUSDT",),
        timeframe="15m",
        session_id=session_id,
    )


async def _process(runner: PaperRunner, candles: list[Candle]) -> None:
    for c in candles:
        await runner.handle_candle("ETHUSDT", TF, c)


async def test_upsert_paper_session_scoped(session: AsyncSession) -> None:
    repo = SqlAlchemyMarketCandleRepository(session)
    candle = _candle(0, 100.0)
    await repo.upsert_paper("sess-A", "ETHUSDT", TF, [candle])
    await repo.upsert_paper("sess-B", "ETHUSDT", TF, [candle])
    await session.commit()

    assert await repo.last_persisted_ms("sess-A", "ETHUSDT", TF) == 0
    assert await repo.last_persisted_ms("sess-B", "ETHUSDT", TF) == 0
    rows_a = await repo.session_range("sess-A", "ETHUSDT", TF, 0, TF_MS)
    rows_b = await repo.session_range("sess-B", "ETHUSDT", TF, 0, TF_MS)
    assert [c.timestamp_ms for c in rows_a] == [0]
    assert [c.timestamp_ms for c in rows_b] == [0]

    # Idempotente: re-upsert no duplica.
    inserted = await repo.upsert_paper("sess-A", "ETHUSDT", TF, [candle])
    await session.commit()
    assert inserted == 0


async def test_paper_event_idempotent_add(session: AsyncSession) -> None:
    repo = SqlAlchemyPaperTradeEventRepository(session)
    event = PaperTradeEvent(
        session_id="sess",
        strategy_version="baseline-v1",
        strategy_hash="h",
        decision_source="baseline",
        symbol="ETHUSDT",
        timeframe="15m",
        timestamp_ms=0,
        action="HOLD",
        filled=False,
        risk_reason="",
        exit_reason="",
        exec_price=None,
        quantity=None,
        fee=0.0,
        slippage_cost=0.0,
        equity=1000.0,
        kill_switch_active=False,
    )
    await repo.add(event)
    await repo.add(event)
    await session.commit()
    assert len(await repo.list_session("sess")) == 1


async def test_restart_parity_mid_position(session: AsyncSession) -> None:
    candles = _uptrend(120, step=0.5)
    last_close = 100.0 + 119 * 0.5

    # --- Control: corrida continua ---
    continuous = PaperRunner(
        config=_config("parity-continuous"),
        event_repo=SqlAlchemyPaperTradeEventRepository(session),
        candle_repo=SqlAlchemyMarketCandleRepository(session),
    )
    await _process(continuous, candles)
    equity_continuous = continuous._engine.portfolio.equity(last_close)

    # --- Restart mid-position: primera mitad → commit → restore → segunda mitad ---
    split = 60
    repo_b = SqlAlchemyPaperTradeEventRepository(session)
    candle_b = SqlAlchemyMarketCandleRepository(session)
    system_b = SqlAlchemySystemStateRepository(session)
    first = PaperRunner(
        config=_config("parity-restart"),
        event_repo=repo_b,
        candle_repo=candle_b,
    )
    await _process(first, candles[:split])
    await session.commit()

    restored = await restore_runner(
        config=_config("parity-restart"),
        event_repo=repo_b,
        candle_repo=candle_b,
        system_state_repo=system_b,
        symbol="ETHUSDT",
        timeframe=TF,
    )
    await _process(restored, candles[split:])
    equity_restart = restored._engine.portfolio.equity(last_close)

    assert equity_restart == equity_continuous

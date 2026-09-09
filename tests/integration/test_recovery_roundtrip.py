from sqlalchemy.ext.asyncio import AsyncSession

from application.ports.paper_trading import PaperTradeEvent
from application.services.decision_context import DecisionContext, recompute_decision_contexts
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


async def test_decision_context_persisted_and_roundtrips(session: AsyncSession) -> None:
    candles = _uptrend(80)
    repo = SqlAlchemyPaperTradeEventRepository(session)
    runner = PaperRunner(
        config=_config("ctx-test"),
        event_repo=repo,
        candle_repo=SqlAlchemyMarketCandleRepository(session),
    )
    for c in candles:
        await runner.handle_candle("ETHUSDT", TF, c)
    await session.commit()

    events = await repo.list_session("ctx-test")
    assert len(events) == len(candles)
    assert all(e.decision_context is not None for e in events)

    recomputed = recompute_decision_contexts(candles)
    for event, expected in zip(events, recomputed, strict=True):
        assert event.decision_context is not None
        assert DecisionContext.from_dict(event.decision_context) == expected


async def test_crash_after_commit_overlap_replayed_candle_is_noop(session: AsyncSession) -> None:
    """Crash tras commit: la vela reentregada (overlap REST/WS) no duplica evento,
    fill ni contabilidad, y el estado reconstruido es idéntico al de antes del overlap.

    Secuencia: candle procesado → commit → crash → restore (replay) → la misma vela
    reaparece (overlap) → NO evento duplicado, NO fill duplicado, NO doble contabilidad,
    estado == estado previo al overlap (la vela reentregada es no-op).
    """
    candles = _uptrend(80, step=0.5)
    split = 40

    repo = SqlAlchemyPaperTradeEventRepository(session)
    candle_repo = SqlAlchemyMarketCandleRepository(session)
    system = SqlAlchemySystemStateRepository(session)

    first = PaperRunner(
        config=_config("crash-after-commit"),
        event_repo=repo,
        candle_repo=candle_repo,
    )
    await _process(first, candles[:split])
    await session.commit()

    # Crash + restart: reconstruye desde lo committeado.
    restored = await restore_runner(
        config=_config("crash-after-commit"),
        event_repo=repo,
        candle_repo=candle_repo,
        system_state_repo=system,
        symbol="ETHUSDT",
        timeframe=TF,
    )
    state_before = _engine_snapshot(restored)

    # Overlap: la última vela committeada reaparece (WS/REST re-entrega).
    await restored.handle_candle("ETHUSDT", TF, candles[split - 1])
    await session.commit()

    state_after = _engine_snapshot(restored)
    events = await repo.list_session("crash-after-commit")

    # Sin evento duplicado (la vela reentregada no genera evento nuevo).
    assert len(events) == split
    # La vela reentregada es no-op: sin doble contabilidad ni mutación de estado.
    assert state_after == state_before


def _engine_snapshot(runner: PaperRunner) -> tuple[float, ...]:
    """Fotografía del estado contable + trackers deterministas del runner."""
    engine = runner._engine
    strategy = runner._strategy
    return (
        round(engine.portfolio.cash, 12),
        round(engine.portfolio.position, 12),
        round(engine.portfolio.realized_pnl, 12),
        round(engine.realized_pnl_today, 12),
        round(strategy.ema_fast or 0.0, 12),
        round(strategy.ema_slow or 0.0, 12),
        round(strategy.rsi or 0.0, 12),
    )

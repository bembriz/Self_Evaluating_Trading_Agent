"""Unit tests — 16c.5a Duplicate Candle State Idempotency (D3).

Verifica el contrato temporal del paper-runner para una vela entrante con
timestamp T frente al último timestamp procesado:

- T < last → ``OutOfOrderTimestampError``
- T == last, vela idéntica → IDEMPOTENT_NO_OP (ninguna mutación de estado)
- T == last, payload distinto → ``DuplicateCandleError`` (inconsistencia de datos)
- T > last → procesamiento normal

La garantía es que una vela ya procesada no vuelva a avanzar estado mutable en
memoria (EMA/RSI/ATR/regime/deque/engine/portfolio/risk/counters/persistencia).
"""

from __future__ import annotations

from typing import Any

import pytest

from application.ports.paper_trading import PaperTradeEvent
from application.services.paper_engine import OutOfOrderTimestampError
from application.services.paper_runner import (
    DuplicateCandleError,
    PaperRunner,
    PaperRunnerConfig,
)
from domain.market.candle import Candle, Timeframe
from domain.market.stream import KlineUpdate
from domain.trading.signal import Action
from domain.trading.strategy import PrecomputedStrategy

SYMBOL = "ETHUSDT"
TF = Timeframe.M15
TF_MS = TF.minutes * 60_000
_WARMUP = 15  # velas para completar el warmup de ATR


def _candle(i: int, close: float) -> Candle:
    return Candle(i * TF_MS, close - 1.0, close + 1.0, close - 2.0, close, 10.0, 1000.0)


def _kline(i: int, close: float) -> KlineUpdate:
    return KlineUpdate(
        SYMBOL, TF, i * TF_MS, close - 1.0, close + 1.0, close - 2.0, close, 10.0, 1000.0, True
    )


class FakeRepo:
    def __init__(self) -> None:
        self.events: list[PaperTradeEvent] = []

    async def add(self, event: PaperTradeEvent) -> None:
        key = (event.session_id, event.symbol, event.timeframe, event.timestamp_ms)
        if any((e.session_id, e.symbol, e.timeframe, e.timestamp_ms) == key for e in self.events):
            return
        self.events.append(event)

    async def list_session(self, session_id: str) -> list[PaperTradeEvent]:
        return [e for e in self.events if e.session_id == session_id]


class FakeCandleRepo:
    def __init__(self) -> None:
        self.upserted: list[tuple[str, str, str, int]] = []

    async def upsert(self, symbol: str, timeframe: Timeframe, candles: list[Candle]) -> int:
        return 0

    async def count(self, symbol: str, timeframe: Timeframe) -> int:
        return 0

    async def range(
        self, symbol: str, timeframe: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        return []

    async def upsert_paper(
        self, session_id: str, symbol: str, timeframe: Timeframe, candles: list[Candle]
    ) -> int:
        for c in candles:
            key = (session_id, symbol, timeframe.label, c.timestamp_ms)
            if key not in self.upserted:
                self.upserted.append(key)
        return 0

    async def session_range(self, *args: Any, **kwargs: Any) -> list[Candle]:
        return []

    async def last_persisted_ms(self, *args: Any, **kwargs: Any) -> int | None:
        return None


def _config() -> PaperRunnerConfig:
    return PaperRunnerConfig(
        trading_mode="paper",
        live_trading_enabled=False,
        symbols=(SYMBOL,),
        timeframe="15m",
        session_id="dup-sess",
    )


def _runner(actions: list[Action], repo: FakeRepo | None = None) -> PaperRunner:
    return PaperRunner(
        config=_config(),
        event_repo=repo or FakeRepo(),
        candle_repo=FakeCandleRepo(),
        strategy=PrecomputedStrategy(actions),  # type: ignore[arg-type]
    )


def _snapshot(runner: PaperRunner) -> tuple[Any, ...]:
    engine = runner._engine
    strategy = runner._strategy
    pos = engine.position
    return (
        engine.portfolio.cash,
        engine.portfolio.position,
        engine.portfolio.avg_entry,
        engine.portfolio.realized_pnl,
        pos.quantity if pos is not None else None,
        pos.entry_price if pos is not None else None,
        pos.stop_loss if pos is not None else None,
        engine.realized_pnl_today,
        engine.daily_loss_active,
        engine.peak_equity,
        getattr(strategy, "ema_fast", None),
        getattr(strategy, "ema_slow", None),
        getattr(strategy, "rsi", None),
        runner._atr_trackers[SYMBOL].value,
        runner._regime_trackers[SYMBOL].rejected_candidates,
    )


def _assert_unchanged(before: tuple[Any, ...], after: tuple[Any, ...]) -> None:
    for b, a in zip(before, after, strict=True):
        if b is None or a is None or isinstance(b, bool):
            assert b is a, f"state changed: {b!r} -> {a!r}"
        else:
            assert b == a, f"state changed: {b!r} -> {a!r}"


async def test_duplicate_same_candle_is_idempotent_noop() -> None:
    """T == last con vela idéntica: estado completo sin cambios y sin evento."""
    n = _WARMUP + 5
    actions = [Action.HOLD] * _WARMUP + [Action.BUY] + [Action.HOLD] * 4
    closes = [100.0] * _WARMUP + [100.0] + [101.0] * 4
    repo = FakeRepo()
    runner = _runner(actions, repo=repo)
    for i in range(n):
        await runner.handle_candle(SYMBOL, TF, _candle(i, closes[i]))

    before = _snapshot(runner)
    result = await runner.handle_candle(SYMBOL, TF, _candle(n - 1, closes[n - 1]))
    after = _snapshot(runner)

    assert result is None
    assert len(repo.events) == n
    _assert_unchanged(before, after)


async def test_duplicate_different_candle_raises() -> None:
    """T == last con payload distinto: inconsistencia de datos → STOP."""
    n = _WARMUP + 5
    actions = [Action.HOLD] * n
    closes = [100.0] * n
    runner = _runner(actions)
    for i in range(n):
        await runner.handle_candle(SYMBOL, TF, _candle(i, closes[i]))

    last = n - 1
    different = Candle(last * TF_MS, 99.0, 101.0, 98.0, 100.5, 10.0, 1000.0)
    with pytest.raises(DuplicateCandleError):
        await runner.handle_candle(SYMBOL, TF, different)


async def test_out_of_order_raises() -> None:
    """T < last → OutOfOrderTimestampError."""
    n = _WARMUP + 5
    actions = [Action.HOLD] * n
    runner = _runner(actions)
    for i in range(n):
        await runner.handle_candle(SYMBOL, TF, _candle(i, 100.0))

    with pytest.raises(OutOfOrderTimestampError):
        await runner.handle_candle(SYMBOL, TF, _candle(n - 2, 100.0))


async def test_duplicate_does_not_create_event() -> None:
    n = _WARMUP + 3
    repo = FakeRepo()
    runner = _runner([Action.HOLD] * n, repo=repo)
    for i in range(n):
        await runner.handle_candle(SYMBOL, TF, _candle(i, 100.0))
    assert len(repo.events) == n

    await runner.handle_candle(SYMBOL, TF, _candle(n - 1, 100.0))
    assert len(repo.events) == n


async def test_duplicate_buy_does_not_create_second_fill() -> None:
    """La vela BUY reentregada no duplica el fill ni la posición."""
    n = _WARMUP + 1
    actions = [Action.HOLD] * _WARMUP + [Action.BUY]
    closes = [100.0] * _WARMUP + [100.0]
    repo = FakeRepo()
    runner = _runner(actions, repo=repo)
    for i in range(n):
        await runner.handle_candle(SYMBOL, TF, _candle(i, closes[i]))

    assert runner._engine.portfolio.position > 0
    fills_before = sum(1 for e in repo.events if e.filled)
    pos_before = runner._engine.portfolio.position
    cash_before = runner._engine.portfolio.cash

    await runner.handle_candle(SYMBOL, TF, _candle(_WARMUP, 100.0))  # BUY reentregada

    assert sum(1 for e in repo.events if e.filled) == fills_before
    assert runner._engine.portfolio.position == pos_before
    assert runner._engine.portfolio.cash == cash_before


async def test_duplicate_does_not_advance_trackers() -> None:
    """La vela duplicada no avanza EMA/RSI/ATR/regime (estrategia baseline real)."""
    n = 60
    closes = [100.0 + i * 0.5 for i in range(n)]
    runner = PaperRunner(config=_config(), event_repo=FakeRepo(), candle_repo=FakeCandleRepo())
    for i in range(n):
        await runner.handle_candle(SYMBOL, TF, _candle(i, closes[i]))

    ema_fast = runner._strategy.ema_fast
    ema_slow = runner._strategy.ema_slow
    rsi = runner._strategy.rsi
    atr = runner._atr_trackers[SYMBOL].value
    regime_rejected = runner._regime_trackers[SYMBOL].rejected_candidates

    await runner.handle_candle(SYMBOL, TF, _candle(n - 1, closes[n - 1]))

    assert runner._strategy.ema_fast == ema_fast
    assert runner._strategy.ema_slow == ema_slow
    assert runner._strategy.rsi == rsi
    assert runner._atr_trackers[SYMBOL].value == atr
    assert runner._regime_trackers[SYMBOL].rejected_candidates == regime_rejected


async def test_duplicate_kline_returns_none_no_processed_semantics() -> None:
    """Un KlineUpdate duplicado devuelve None (no incrementa processed/candles)."""
    n = _WARMUP + 3
    repo = FakeRepo()
    runner = _runner([Action.HOLD] * n, repo=repo)
    for i in range(n):
        assert await runner.handle_kline(_kline(i, 100.0)) is not None

    assert await runner.handle_kline(_kline(n - 1, 100.0)) is None
    assert len(repo.events) == n

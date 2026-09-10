"""Tests RED — corrección max_daily_loss (Fase 16b).

Cubre: reset diario UTC, guard solo sobre BUY, out-of-order de timestamps,
contadores separados y paridad Paper↔Replay. Deben FALLAR antes del fix.
"""

from __future__ import annotations

import pytest

from application.services.paper_engine import OutOfOrderTimestampError, PaperEngine
from application.services.paper_runner import PaperRunner, PaperRunnerConfig
from domain.market.candle import Candle, Timeframe
from domain.market.stream import KlineUpdate
from domain.risk.config import RiskConfig
from domain.time.day import MS_PER_DAY, utc_day_index
from domain.trading.decision import TradingDecision
from domain.trading.signal import Action, Intensity, Signal

D10 = 10 * MS_PER_DAY
D11 = 11 * MS_PER_DAY


@pytest.fixture
def cfg() -> RiskConfig:
    from dataclasses import replace

    return replace(RiskConfig(), max_position_allocation=1.0)


def _decision(action: Action, ts: int) -> TradingDecision:
    return TradingDecision(
        timestamp_ms=ts, action=action, confidence=0.8, intensity=Intensity.MEDIUM
    )


# ---------------------------------------------------------------- day abstraction
def test_utc_day_index_boundaries() -> None:
    assert utc_day_index(0) == 0
    assert utc_day_index(MS_PER_DAY - 1) == 0
    assert utc_day_index(MS_PER_DAY) == 1
    assert utc_day_index(2 * MS_PER_DAY) == 2


# ---------------------------------------------------------------- reset diario
def test_realized_resets_at_utc_day_boundary(cfg: RiskConfig) -> None:
    engine = PaperEngine(config=cfg)
    engine.on_price(decision=_decision(Action.HOLD, D10), price=2000.0, atr=10.0, timestamp_ms=D10)
    engine._realized_pnl_today = -10.0  # pérdida del día D10 (sembrada)

    engine.on_price(decision=_decision(Action.HOLD, D11), price=2000.0, atr=10.0, timestamp_ms=D11)

    assert engine.realized_pnl_today == 0.0


def test_buy_evaluated_again_after_reset(cfg: RiskConfig) -> None:
    engine = PaperEngine(config=cfg)
    engine.on_price(decision=_decision(Action.HOLD, D10), price=2000.0, atr=10.0, timestamp_ms=D10)
    engine._realized_pnl_today = -20.0  # día D10 tocó el límite

    # Nueva frontera de día → reset; el BUY vuelve a poder evaluarse.
    event = engine.on_price(
        decision=_decision(Action.BUY, D11), price=2000.0, atr=10.0, timestamp_ms=D11
    )

    assert event.filled is True
    assert engine.position is not None


def test_open_position_across_midnight_does_not_realize(cfg: RiskConfig) -> None:
    engine = PaperEngine(config=cfg)
    engine.on_price(decision=_decision(Action.BUY, D10), price=2000.0, atr=10.0, timestamp_ms=D10)
    assert engine.realized_pnl_today == 0.0

    engine.on_price(decision=_decision(Action.HOLD, D11), price=2010.0, atr=10.0, timestamp_ms=D11)

    # El unrealized de la posición abierta NO se marca a mercado en realized diario.
    assert engine.realized_pnl_today == 0.0
    assert engine.position is not None


def test_two_consecutive_days_independent(cfg: RiskConfig) -> None:
    engine = PaperEngine(config=cfg)
    # Día D10: pérdida realizada vía stop.
    engine.on_price(decision=_decision(Action.BUY, D10), price=2000.0, atr=10.0, timestamp_ms=D10)
    engine.on_price(
        decision=_decision(Action.HOLD, D10 + 900_000),
        price=1970.0,
        atr=10.0,
        timestamp_ms=D10 + 900_000,
    )
    r10 = engine.realized_pnl_today
    assert r10 < 0

    # Día D11: abre en 0 (independiente).
    engine.on_price(decision=_decision(Action.HOLD, D11), price=2000.0, atr=10.0, timestamp_ms=D11)
    assert engine.realized_pnl_today == 0.0

    engine.on_price(
        decision=_decision(Action.BUY, D11 + 900_000),
        price=2000.0,
        atr=10.0,
        timestamp_ms=D11 + 900_000,
    )
    engine.on_price(
        decision=_decision(Action.HOLD, D11 + 2 * 900_000),
        price=1970.0,
        atr=10.0,
        timestamp_ms=D11 + 2 * 900_000,
    )
    # Independencia: el acumulado DIARIO es solo el net de hoy; la SESIÓN suma ambos días.
    t0, t1 = engine.portfolio.trades
    assert t0.net_pnl == pytest.approx(r10)
    assert engine.realized_pnl_today == pytest.approx(t1.net_pnl)
    assert engine.portfolio.realized_pnl == pytest.approx(t0.net_pnl + t1.net_pnl)


# -------------------------------------------------- reducción de riesgo tras el límite
def test_stop_loss_exit_allowed_after_daily_limit(cfg: RiskConfig) -> None:
    engine = PaperEngine(config=cfg)
    engine.on_price(decision=_decision(Action.BUY, D10), price=2000.0, atr=10.0, timestamp_ms=D10)
    engine._realized_pnl_today = -20.0  # día ya tocó el límite

    event = engine.on_price(
        decision=_decision(Action.HOLD, D10 + 900_000),
        price=1970.0,
        atr=10.0,
        timestamp_ms=D10 + 900_000,
    )

    assert event.exit_reason == "stop_loss"
    assert event.filled is True


def test_take_profit_exit_allowed_after_daily_limit(cfg: RiskConfig) -> None:
    engine = PaperEngine(config=cfg)
    engine.on_price(decision=_decision(Action.BUY, D10), price=2000.0, atr=10.0, timestamp_ms=D10)
    engine._realized_pnl_today = -20.0

    event = engine.on_price(
        decision=_decision(Action.HOLD, D10 + 900_000),
        price=2045.0,
        atr=10.0,
        timestamp_ms=D10 + 900_000,
    )

    assert event.exit_reason == "take_profit"
    assert event.filled is True


def test_hold_after_limit_has_no_risk_reason(cfg: RiskConfig) -> None:
    engine = PaperEngine(config=cfg)
    engine.on_price(decision=_decision(Action.HOLD, D10), price=2000.0, atr=10.0, timestamp_ms=D10)
    engine._realized_pnl_today = -20.0

    event = engine.on_price(
        decision=_decision(Action.HOLD, D10 + 900_000),
        price=2000.0,
        atr=10.0,
        timestamp_ms=D10 + 900_000,
    )

    assert event.filled is False
    assert event.risk_reason == ""


# ---------------------------------------------------------------- fees / slippage
def test_fees_and_slippage_still_included_after_reset(cfg: RiskConfig) -> None:
    engine = PaperEngine(config=cfg)
    engine.on_price(decision=_decision(Action.BUY, D10), price=2000.0, atr=10.0, timestamp_ms=D10)
    engine.on_price(
        decision=_decision(Action.SELL, D10 + 900_000),
        price=2020.0,
        atr=10.0,
        timestamp_ms=D10 + 900_000,
    )
    net_day10 = engine.realized_pnl_today
    assert net_day10 > 0
    assert engine.portfolio.total_fees > 0  # fees netos acumulados
    assert net_day10 < (2020.0 - 2000.0) * engine.portfolio.trades[0].quantity  # < gross

    # Reset de día no borra las fees/slippage ya devengadas del portfolio.
    engine.on_price(decision=_decision(Action.HOLD, D11), price=2000.0, atr=10.0, timestamp_ms=D11)
    assert engine.realized_pnl_today == 0.0
    assert engine.portfolio.total_fees > 0


# ---------------------------------------------------------------- contadores separados
def test_counters_separated(cfg: RiskConfig) -> None:
    engine = PaperEngine(config=cfg)
    engine.on_price(decision=_decision(Action.HOLD, D10), price=2000.0, atr=10.0, timestamp_ms=D10)
    assert engine.orders_rejected == 0
    assert engine.daily_loss_triggered == 0
    assert engine.daily_loss_active_cycles == 0

    engine._realized_pnl_today = -20.0
    # HOLD bajo daily-loss activo → ciclo activo (no orden rechazada).
    engine.on_price(
        decision=_decision(Action.HOLD, D10 + 900_000),
        price=2000.0,
        atr=10.0,
        timestamp_ms=D10 + 900_000,
    )
    assert engine.daily_loss_active_cycles == 1
    assert engine.orders_rejected == 0

    # BUY rechazado por daily loss → orden rechazada + trigger.
    engine.on_price(
        decision=_decision(Action.BUY, D10 + 2 * 900_000),
        price=2000.0,
        atr=10.0,
        timestamp_ms=D10 + 2 * 900_000,
    )
    assert engine.orders_rejected == 1
    assert engine.daily_loss_triggered == 1

    # SELL sin posición → orden rechazada (no trigger).
    engine.on_price(
        decision=_decision(Action.SELL, D10 + 3 * 900_000),
        price=2000.0,
        atr=10.0,
        timestamp_ms=D10 + 3 * 900_000,
    )
    assert engine.orders_rejected == 2
    assert engine.daily_loss_triggered == 1


# ---------------------------------------------------------------- out-of-order
def test_out_of_order_timestamp_raises(cfg: RiskConfig) -> None:
    engine = PaperEngine(config=cfg)
    engine.on_price(
        decision=_decision(Action.HOLD, 1000), price=2000.0, atr=10.0, timestamp_ms=1000
    )

    with pytest.raises(OutOfOrderTimestampError):
        engine.on_price(
            decision=_decision(Action.HOLD, 900), price=2000.0, atr=10.0, timestamp_ms=900
        )


def test_out_of_order_does_not_mutate_state(cfg: RiskConfig) -> None:
    engine = PaperEngine(config=cfg)
    engine.on_price(decision=_decision(Action.BUY, 1000), price=2000.0, atr=10.0, timestamp_ms=1000)
    realized_before = engine.realized_pnl_today

    with pytest.raises(OutOfOrderTimestampError):
        engine.on_price(
            decision=_decision(Action.SELL, 900), price=2000.0, atr=10.0, timestamp_ms=900
        )

    assert engine.position is not None  # posición intacta
    assert engine.realized_pnl_today == realized_before

    # Timestamp igual es válido (no es "menor").
    engine.on_price(
        decision=_decision(Action.HOLD, 1000), price=2000.0, atr=10.0, timestamp_ms=1000
    )


# ---------------------------------------------------------------- paridad Paper↔Replay
class _AlwaysBuyStrategy:
    version = "test-always-buy-v1"

    def on_candle(self, candle: Candle) -> Signal:
        return Signal(timestamp_ms=candle.timestamp_ms, action=Action.BUY, reason="test")


class _Repo:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def add(self, event: object) -> None:
        self.events.append(event)

    async def list_session(self, session_id: str) -> list[object]:
        return self.events


def _kline(ts: int, confirm: bool = True) -> KlineUpdate:
    return KlineUpdate(
        "ETHUSDT", Timeframe.M15, ts, 2000.0, 2000.0, 2000.0, 2000.0, 10.0, 1000.0, confirm
    )


async def test_paper_runner_shares_daily_reset_semantics() -> None:
    """El runner WS (Paper) y el replay (paper_session→PaperEngine) comparten reset."""
    cfg = PaperRunnerConfig(
        trading_mode="paper",
        live_trading_enabled=False,
        symbols=("ETHUSDT",),
        timeframe="15m",
        session_id="t",
        decision_source="baseline",
    )
    runner = PaperRunner(
        config=cfg,
        event_repo=_Repo(),  # type: ignore[arg-type]
        strategy=_AlwaysBuyStrategy(),  # type: ignore[arg-type]
    )
    runner._engine._realized_pnl_today = -10.0

    await runner.handle_kline(_kline(D10))  # día D10: establece el día, no resetea
    await runner.handle_kline(_kline(D11))  # frontera → reset a 0

    assert runner._engine.realized_pnl_today == 0.0

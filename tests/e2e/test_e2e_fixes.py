"""E2E automatizados de los fixes de Fase 16b (bug #1 y bug #2).

Cubren el pipeline real PaperEngine (decisión → RiskEngine → fill con slippage →
Portfolio → métricas → equity) sin mockear el motor:

- E2E-1: max_daily_loss → BUY blocked → HOLD allowed → SELL/stop allowed →
         UTC rollover → reset → BUY allowed.
- E2E-2: BUY (slippage en exec_price) → SELL → fees → portfolio → metrics →
         final_equity → reconciliation residual == 0.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from application.services.paper_engine import PaperEngine
from domain.evaluation.metrics import compute_metrics
from domain.risk.config import RiskConfig
from domain.time.day import MS_PER_DAY
from domain.trading.decision import TradingDecision
from domain.trading.signal import Action, Intensity

D0 = 100 * MS_PER_DAY  # día calendario UTC arbitrario (índice 100)


def _cfg() -> RiskConfig:
    return replace(RiskConfig(), max_position_allocation=1.0)


def _decision(action: Action, ts: int, intensity: Intensity = Intensity.HIGH) -> TradingDecision:
    return TradingDecision(timestamp_ms=ts, action=action, confidence=1.0, intensity=intensity)


def test_e2e_1_max_daily_loss_full_flow() -> None:
    engine = PaperEngine(config=_cfg())

    # Día N: BUY llena posición (HIGH, atr=50 → stop=1900).
    e = engine.on_price(decision=_decision(Action.BUY, D0), price=2000.0, atr=50.0, timestamp_ms=D0)
    assert e.filled is True
    assert engine.position is not None

    # stop-loss permitido → realiza pérdida y activa el límite diario.
    e = engine.on_price(
        decision=_decision(Action.HOLD, D0 + 900_000),
        price=1890.0,
        atr=50.0,
        timestamp_ms=D0 + 900_000,
    )
    assert e.exit_reason == "stop_loss"
    assert e.filled is True
    assert engine.daily_loss_active is True

    # BUY bloqueado por daily loss.
    e = engine.on_price(
        decision=_decision(Action.BUY, D0 + 2 * 900_000),
        price=2000.0,
        atr=50.0,
        timestamp_ms=D0 + 2 * 900_000,
    )
    assert e.filled is False
    assert e.risk_reason == "max_daily_loss"

    # HOLD permitido (no es orden rechazada).
    e = engine.on_price(
        decision=_decision(Action.HOLD, D0 + 3 * 900_000),
        price=2000.0,
        atr=50.0,
        timestamp_ms=D0 + 3 * 900_000,
    )
    assert e.filled is False
    assert e.risk_reason == ""

    # SELL permitido (no gateado por daily loss): sin posición → no_position_to_reduce.
    e = engine.on_price(
        decision=_decision(Action.SELL, D0 + 4 * 900_000),
        price=2000.0,
        atr=50.0,
        timestamp_ms=D0 + 4 * 900_000,
    )
    assert e.risk_reason == "no_position_to_reduce"

    # UTC rollover → reset del acumulador diario.
    assert engine.realized_pnl_today < 0
    e = engine.on_price(
        decision=_decision(Action.HOLD, D0 + MS_PER_DAY),
        price=2000.0,
        atr=50.0,
        timestamp_ms=D0 + MS_PER_DAY,
    )
    assert engine.realized_pnl_today == 0.0
    assert engine.daily_loss_active is False

    # BUY vuelve a permitirse tras el reset.
    e = engine.on_price(
        decision=_decision(Action.BUY, D0 + MS_PER_DAY + 900_000),
        price=2000.0,
        atr=50.0,
        timestamp_ms=D0 + MS_PER_DAY + 900_000,
    )
    assert e.filled is True
    assert engine.position is not None


def test_e2e_2_accounting_roundtrip_residual_zero() -> None:
    cfg = _cfg()
    engine = PaperEngine(config=cfg)

    # BUY con slippage embebida en exec_price (exec > price).
    e = engine.on_price(
        decision=_decision(Action.BUY, 1000), price=2000.0, atr=50.0, timestamp_ms=1000
    )
    assert e.filled is True
    assert e.fill is not None
    assert e.fill.exec_price > 2000.0  # slippage en ejecución

    # SELL cierra la posición.
    e = engine.on_price(
        decision=_decision(Action.SELL, 2000), price=2100.0, atr=50.0, timestamp_ms=2000
    )
    assert e.filled is True
    assert engine.position is None

    # Métricas (mismo accounting que Portfolio).
    final_equity = engine.mark_to_market(price=2100.0)
    m = compute_metrics(engine.portfolio.trades, [cfg.capital, final_equity], periods_per_year=8760)
    assert m.fees > 0
    assert m.slippage > 0  # analítica (embebida en gross)
    assert m.net_pnl == pytest.approx(engine.portfolio.realized_pnl)

    # Reconciliación: equity final = initial + realized (residual 0, posición plana).
    assert engine.portfolio.position == 0.0
    residual = final_equity - cfg.capital - engine.portfolio.realized_pnl
    assert residual == pytest.approx(0.0, abs=1e-9)

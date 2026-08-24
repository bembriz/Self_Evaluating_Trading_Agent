"""Tests del sizing híbrido (PRD §21): intensity → monto real vía riesgo+ATR."""

from dataclasses import replace

import pytest

from domain.risk.config import RiskConfig
from domain.risk.sizing import PositionSize, compute_position_size


@pytest.fixture
def cfg() -> RiskConfig:
    return RiskConfig()


@pytest.fixture
def cfg_sin_cap() -> RiskConfig:
    """Sin cap de asignación para aislar la fórmula de riesgo."""
    return replace(RiskConfig(), max_position_allocation=1.0)


def test_budget_by_intensity(cfg: RiskConfig) -> None:
    assert cfg.risk_budget_pct("low") == 0.005
    assert cfg.risk_budget_pct("medium") == 0.01
    assert cfg.risk_budget_pct("high") == 0.02
    assert cfg.risk_budget_pct("desconocida") == cfg.medium_risk_pct  # fail-safe medio
    from domain.trading.signal import Intensity

    assert cfg.risk_budget_pct(Intensity.HIGH) == 0.02  # acepta enum


def test_size_from_risk_and_stop_distance(cfg_sin_cap: RiskConfig) -> None:
    # MEDIUM: riesgo = 1000*0.01 = 10 USDT; distancia = 2*ATR = 20 ⇒ qty = 0.5.
    size = compute_position_size(
        intensity="medium", atr=10.0, price=2000.0, current_drawdown=0.0, config=cfg_sin_cap
    )
    assert isinstance(size, PositionSize)
    assert size.quantity == pytest.approx(0.5)
    assert size.notional == pytest.approx(1000.0)
    assert size.stop_distance == pytest.approx(20.0)
    assert size.risk_amount == pytest.approx(10.0)


def test_notional_cap_limits_quantity(cfg: RiskConfig) -> None:
    # Cap de asignación: 2%*1000 = 20 USDT ⇒ qty = 20/price.
    size = compute_position_size(
        intensity="high", atr=1.0, price=1000.0, current_drawdown=0.0, config=cfg
    )
    assert size.capped is True
    assert size.notional == pytest.approx(20.0)
    assert size.quantity == pytest.approx(0.02)


def test_uncapped_when_small(cfg: RiskConfig) -> None:
    size = compute_position_size(
        intensity="low", atr=100.0, price=100.0, current_drawdown=0.0, config=cfg
    )
    assert size.capped is False
    assert size.notional == pytest.approx(size.quantity * 100.0)
    assert size.notional <= cfg.max_position_allocation * cfg.capital


def test_zero_or_negative_atr_gives_no_size(cfg: RiskConfig) -> None:
    for atr in (0.0, -5.0):
        size = compute_position_size(
            intensity="medium", atr=atr, price=2000.0, current_drawdown=0.0, config=cfg
        )
        assert size.quantity == 0.0
        assert size.notional == 0.0
        assert size.capped is False


def test_non_positive_price_gives_no_size(cfg: RiskConfig) -> None:
    size = compute_position_size(
        intensity="medium", atr=10.0, price=0.0, current_drawdown=0.0, config=cfg
    )
    assert size.quantity == 0.0


def test_drawdown_scales_down_linearly(cfg_sin_cap: RiskConfig) -> None:
    def q(dd: float) -> float:
        return compute_position_size(
            intensity="medium", atr=10.0, price=2000.0, current_drawdown=dd, config=cfg_sin_cap
        ).quantity

    full, half = q(0.0), q(0.025)
    assert half == pytest.approx(full * 0.5)
    assert q(0.05) == 0.0
    assert q(0.08) == 0.0  # sobre el máximo: sin exposición


def test_leverage_never_increases_notional(cfg: RiskConfig) -> None:
    size = compute_position_size(
        intensity="high", atr=1.0, price=1000.0, current_drawdown=0.0, config=cfg
    )
    assert size.notional <= cfg.capital * (1.0 - cfg.leverage)


def test_capped_risk_amount_reflects_effective_exposure(cfg_sin_cap: RiskConfig) -> None:
    """Tras el cap, el riesgo efectivo es menor que el presupuesto teórico."""
    capped_cfg = replace(cfg_sin_cap, max_position_allocation=0.004)
    size = compute_position_size(
        intensity="medium", atr=10.0, price=2000.0, current_drawdown=0.0, config=capped_cfg
    )
    assert size.capped is True
    assert size.risk_amount < capped_cfg.capital * capped_cfg.medium_risk_pct

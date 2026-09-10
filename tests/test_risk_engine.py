"""Tests del RiskEngine (PRD §22, §24): prioridad absoluta y todas las ramas."""

from dataclasses import replace

import pytest

from domain.risk.config import RiskConfig
from domain.risk.engine import (
    PortfolioRiskState,
    RiskEngine,
    TradeProposal,
)
from domain.risk.guards import KillSwitchState
from domain.risk.sizing import compute_position_size
from domain.trading.signal import Action, Intensity


@pytest.fixture
def cfg() -> RiskConfig:
    return RiskConfig()


def _proposal(
    action: Action = Action.BUY,
    intensity: Intensity = Intensity.MEDIUM,
    price: float = 2000.0,
    atr: float | None = 10.0,
) -> TradeProposal:
    return TradeProposal(
        action=action, intensity=intensity, price=price, atr=atr, timestamp_ms=1000
    )


def _state(**overrides: object) -> PortfolioRiskState:
    base = dict(
        open_positions=0,
        realized_pnl_today=0.0,
        peak_equity=1000.0,
        equity=1000.0,
        kill_switch=KillSwitchState(active=False),
    )
    base.update(overrides)
    return PortfolioRiskState(**base)  # type: ignore[arg-type]


def test_buy_happy_path_returns_size_stop_tp(cfg: RiskConfig) -> None:
    verdict = RiskEngine(cfg).evaluate(_proposal(), _state())
    assert verdict.approved is True
    assert verdict.reason == "ok"
    assert verdict.size is not None and verdict.size.quantity > 0
    # Stop = precio − 2×ATR; TP = entrada + 2R.
    assert verdict.stop_loss == pytest.approx(2000.0 - 20.0)
    assert verdict.take_profit == pytest.approx(2000.0 + 40.0)


def test_priority_kill_switch_first(cfg: RiskConfig) -> None:
    state = _state(
        kill_switch=KillSwitchState(active=True, reason="emergencia"),
        realized_pnl_today=-999.0,  # también violaría daily loss: gana kill switch
        equity=900.0,  # y drawdown
    )
    v = RiskEngine(cfg).evaluate(_proposal(), state)
    assert v.approved is False
    assert v.reason == "kill_switch"


def test_priority_drawdown_before_daily_loss(cfg: RiskConfig) -> None:
    state = _state(equity=950.0, realized_pnl_today=-50.0)
    v = RiskEngine(cfg).evaluate(_proposal(), state)
    assert v.approved is False
    assert v.reason == "max_drawdown"


def test_daily_loss_blocks_at_exact_threshold(cfg: RiskConfig) -> None:
    state = _state(realized_pnl_today=-20.0)
    v = RiskEngine(cfg).evaluate(_proposal(), state)
    assert v.approved is False
    assert v.reason == "max_daily_loss"


def test_drawdown_blocks_at_exact_threshold(cfg: RiskConfig) -> None:
    v = RiskEngine(cfg).evaluate(_proposal(), _state(equity=950.0))
    assert v.approved is False
    assert v.reason == "max_drawdown"


def test_max_open_positions_blocks_second_buy(cfg: RiskConfig) -> None:
    v = RiskEngine(cfg).evaluate(_proposal(), _state(open_positions=1))
    assert v.approved is False
    assert v.reason == "max_open_positions"


def test_sell_reduces_only_without_sizing_requirements(cfg: RiskConfig) -> None:
    """SELL long-only reduce posición; no exige ATR ni sizing."""
    proposal = _proposal(action=Action.SELL, atr=None)
    v = RiskEngine(cfg).evaluate(proposal, _state(open_positions=1))
    assert v.approved is True
    assert v.reason == "reduce"
    assert v.size is None and v.stop_loss is None


def test_sell_without_position_rejected(cfg: RiskConfig) -> None:
    """Long-only: SELL sin posición abierta se rechaza (nada que reducir)."""
    v = RiskEngine(cfg).evaluate(_proposal(action=Action.SELL, atr=None), _state(open_positions=0))
    assert v.approved is False
    assert v.reason == "no_position_to_reduce"


def test_hold_passes_through_without_trade(cfg: RiskConfig) -> None:
    v = RiskEngine(cfg).evaluate(_proposal(action=Action.HOLD), _state())
    assert v.approved is True
    assert v.reason == "no_op"
    assert v.size is None


def test_buy_requires_stop_inputs_when_required(cfg: RiskConfig) -> None:
    for kwargs in ({"atr": None}, {"atr": 0.0}):
        v = RiskEngine(cfg).evaluate(_proposal(atr=kwargs["atr"]), _state())
        assert v.approved is False
        assert v.reason == "stop_unavailable"


def test_buy_ok_without_atr_when_stop_not_required() -> None:
    """Sin exigencia de stop ni ATR: sizing por asignación, sin stop/TP."""
    cfg = replace(RiskConfig(), stop_loss_required=False)
    v = RiskEngine(cfg).evaluate(_proposal(atr=None), _state())
    assert v.approved is True
    assert v.reason == "ok_unstopped"
    assert v.stop_loss is None and v.take_profit is None
    assert v.size is not None
    assert v.size.notional == pytest.approx(0.02 * cfg.capital)


def test_zero_price_without_stop_rejected() -> None:
    cfg = replace(RiskConfig(), stop_loss_required=False)
    v = RiskEngine(cfg).evaluate(_proposal(atr=None, price=0.0), _state())
    assert v.approved is False
    assert v.reason == "zero_size"


def test_zero_size_rejected_when_allocation_is_zero(cfg: RiskConfig) -> None:
    """Asignación máxima 0% ⇒ sizing cero ⇒ entrada rechazada (rama zero_size)."""
    cfg_zero = replace(cfg, max_position_allocation=0.0)
    v = RiskEngine(cfg_zero).evaluate(_proposal(), _state())
    assert v.approved is False
    assert v.reason == "zero_size"


def test_config_version_exposed(cfg: RiskConfig) -> None:
    assert RiskEngine(cfg).config_version == "risk-v1"


def test_zero_drawdown_when_no_peak_yet(cfg: RiskConfig) -> None:
    """Portfolio recién iniciado (pico 0): drawdown 0, entrada normal."""
    v = RiskEngine(cfg).evaluate(_proposal(), _state(peak_equity=0.0, equity=0.0))
    assert v.approved is True


def test_equity_above_peak_means_no_drawdown(cfg: RiskConfig) -> None:
    """Equity sobre el pico histórico ⇒ drawdown 0 en el sizing."""
    v = RiskEngine(cfg).evaluate(_proposal(), _state(peak_equity=900.0, equity=1100.0))
    assert v.approved is True
    assert v.size is not None and v.size.quantity > 0


def test_partial_drawdown_reaches_sizing_scale(cfg: RiskConfig) -> None:
    """Drawdown intermedio (<límite): pasa guards y reduce el tamaño linealmente."""
    state = _state(peak_equity=1000.0, equity=998.0)  # dd = 0.2%
    v = RiskEngine(cfg).evaluate(_proposal(), state)
    assert v.approved is True
    assert v.size is not None
    cfg_sin_cap = replace(cfg, max_position_allocation=1.0)
    full = compute_position_size(
        intensity="medium",
        atr=10.0,
        price=2000.0,
        current_drawdown=0.0,
        config=cfg_sin_cap,
    )
    scaled = compute_position_size(
        intensity="medium",
        atr=10.0,
        price=2000.0,
        current_drawdown=0.002,
        config=cfg_sin_cap,
    )
    assert scaled.quantity == pytest.approx(full.quantity * (1 - 0.002 / 0.05))


def test_engine_uses_latest_config_version(cfg: RiskConfig) -> None:
    custom = replace(cfg, version="risk-v2", stop_atr_multiplier=3.0)
    v = RiskEngine(custom).evaluate(_proposal(atr=10.0), _state())
    assert v.stop_loss == pytest.approx(2000.0 - 30.0)


def test_buy_allowed_below_daily_limit(cfg: RiskConfig) -> None:
    """Pérdida < 2% (umbral) → BUY sigue permitido."""
    v = RiskEngine(cfg).evaluate(_proposal(), _state(realized_pnl_today=-19.99))
    assert v.approved is True
    assert v.reason == "ok"


def test_hold_after_daily_limit_is_noop_not_rejected(cfg: RiskConfig) -> None:
    """HOLD tras alcanzar el límite diario NO es una orden rechazada."""
    v = RiskEngine(cfg).evaluate(_proposal(action=Action.HOLD), _state(realized_pnl_today=-20.0))
    assert v.approved is True
    assert v.reason == "no_op"


def test_sell_with_position_after_daily_limit_reduces(cfg: RiskConfig) -> None:
    """SELL reduce posición incluso con límite diario alcanzado (reduce riesgo)."""
    v = RiskEngine(cfg).evaluate(
        _proposal(action=Action.SELL, atr=None),
        _state(open_positions=1, realized_pnl_today=-20.0),
    )
    assert v.approved is True
    assert v.reason == "reduce"


def test_sell_without_position_after_daily_limit(cfg: RiskConfig) -> None:
    """SELL sin posición tras límite → no_position_to_reduce (NO max_daily_loss)."""
    v = RiskEngine(cfg).evaluate(
        _proposal(action=Action.SELL, atr=None),
        _state(open_positions=0, realized_pnl_today=-20.0),
    )
    assert v.approved is False
    assert v.reason == "no_position_to_reduce"

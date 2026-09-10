"""Tests de los guards de riesgo: daily loss, drawdown y kill switch (PRD §22)."""

import pytest

from domain.risk.config import RiskConfig
from domain.risk.guards import (
    KillSwitch,
    KillSwitchState,
    daily_loss_exceeded,
    drawdown_exceeded,
)


@pytest.fixture
def cfg() -> RiskConfig:
    return RiskConfig()


def test_daily_loss_threshold_exact(cfg: RiskConfig) -> None:
    limit = cfg.capital * cfg.max_daily_loss  # 20 USDT
    assert daily_loss_exceeded(-limit, capital=cfg.capital, config=cfg) is True
    assert daily_loss_exceeded(-(limit - 0.01), capital=cfg.capital, config=cfg) is False
    assert daily_loss_exceeded(0.0, capital=cfg.capital, config=cfg) is False
    assert daily_loss_exceeded(50.0, capital=cfg.capital, config=cfg) is False


def test_drawdown_threshold_exact(cfg: RiskConfig) -> None:
    # Pico 1000; límite 5% ⇒ bloquea con equity <= 950.
    assert drawdown_exceeded(peak_equity=1000.0, equity=950.0, config=cfg) is True
    assert drawdown_exceeded(peak_equity=1000.0, equity=950.01, config=cfg) is False
    assert drawdown_exceeded(peak_equity=1000.0, equity=1000.0, config=cfg) is False


def test_drawdown_with_zero_peak_never_blocks(cfg: RiskConfig) -> None:
    assert drawdown_exceeded(peak_equity=0.0, equity=-10.0, config=cfg) is False


def test_drawdown_equidad_sobre_pico_no_bloquea(cfg: RiskConfig) -> None:
    assert drawdown_exceeded(peak_equity=900.0, equity=1100.0, config=cfg) is False


def test_kill_switch_lifecycle() -> None:
    ks = KillSwitch()
    assert ks.state.active is False
    assert ks.allows_trading() is True

    state = ks.activate(reason="pérdida anómala", timestamp_ms=1234)
    assert isinstance(state, KillSwitchState)
    assert ks.state.active is True
    assert ks.state.reason == "pérdida anómala"
    assert ks.allows_trading() is False

    # Idempotente: reactivar no cambia la razón original.
    ks.activate(reason="otro", timestamp_ms=9999)
    assert ks.state.reason == "pérdida anómala"
    assert ks.state.activated_at_ms == 1234


def test_kill_switch_reset_only_human() -> None:
    ks = KillSwitch().activate_and_return()
    with pytest.raises(PermissionError):
        ks.reset(by="llm")
    ks.reset(by="human", approval_id="APR-001")
    assert ks.allows_trading() is True
    assert ks.state.active is False


def test_kill_switch_restore_persistent_across_restart() -> None:
    first = KillSwitch().activate(reason="dd", timestamp_ms=5)
    restored = KillSwitch(initial_state=first)
    assert restored.allows_trading() is False  # sobrevive al reinicio


def test_kill_switch_state_serialization_roundtrip() -> None:
    state = KillSwitchState(active=True, reason="manual stop", activated_at_ms=42)
    assert KillSwitchState.from_dict(state.to_dict()) == state


def test_kill_switch_state_from_dict_defaults() -> None:
    assert KillSwitchState.from_dict({}) == KillSwitchState()

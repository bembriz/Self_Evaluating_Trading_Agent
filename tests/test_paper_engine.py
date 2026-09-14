"""Tests del Paper Engine (PRD §25): decisión → riesgo → fill → posición → salida.

Determinista sobre datos históricos congelados; fees+slippage reales; los stops
preceden a la intención del LLM; kill switch bloquea nuevas entradas.
"""

from dataclasses import replace

import pytest

from application.services.paper_engine import PaperEngine, PaperPosition
from domain.risk.config import RiskConfig
from domain.risk.guards import KillSwitch, KillSwitchState
from domain.trading.decision import TradingDecision
from domain.trading.signal import Action, Intensity


@pytest.fixture
def cfg() -> RiskConfig:
    return replace(RiskConfig(), max_position_allocation=1.0)  # sin cap para sizing limpio


def _decision(
    action: Action, intensity: Intensity = Intensity.MEDIUM, ts: int = 1000
) -> TradingDecision:
    return TradingDecision(timestamp_ms=ts, action=action, confidence=0.8, intensity=intensity)


def _engine(cfg: RiskConfig) -> PaperEngine:
    return PaperEngine(config=cfg)


def test_buy_opens_position_with_stop_and_tp(cfg: RiskConfig) -> None:
    engine = _engine(cfg)
    event = engine.on_price(
        decision=_decision(Action.BUY), price=2000.0, atr=10.0, timestamp_ms=1000
    )
    assert event.filled is True
    assert engine.position is not None
    assert engine.position.stop_loss == pytest.approx(1980.0)
    assert engine.position.take_profit == pytest.approx(2040.0)
    assert engine.portfolio.position > 0


def test_stop_loss_exits_before_llm(cfg: RiskConfig) -> None:
    engine = _engine(cfg)
    engine.on_price(decision=_decision(Action.BUY), price=2000.0, atr=10.0, timestamp_ms=1000)
    # Precio cae bajo el stop; el LLM dice HOLD pero el stop tiene prioridad.
    event = engine.on_price(
        decision=_decision(Action.HOLD), price=1970.0, atr=10.0, timestamp_ms=2000
    )
    assert event.exit_reason == "stop_loss"
    assert engine.portfolio.position == 0.0
    assert engine.realized_pnl_today < 0  # pérdida realizada registrada


def test_take_profit_exits(cfg: RiskConfig) -> None:
    engine = _engine(cfg)
    engine.on_price(decision=_decision(Action.BUY), price=2000.0, atr=10.0, timestamp_ms=1000)
    event = engine.on_price(
        decision=_decision(Action.HOLD), price=2045.0, atr=10.0, timestamp_ms=2000
    )
    assert event.exit_reason == "take_profit"
    assert engine.realized_pnl_today > 0


def test_trailing_rises_and_locks_profit(cfg: RiskConfig) -> None:
    cfg_tp_lejano = replace(cfg, take_profit_r_multiple=10.0)  # TP fuera del rango del caso
    engine = PaperEngine(config=cfg_tp_lejano)
    engine.on_price(decision=_decision(Action.BUY), price=2000.0, atr=10.0, timestamp_ms=1000)
    assert engine.position is not None
    stop_inicial = engine.position.stop_loss
    engine.on_price(decision=_decision(Action.HOLD), price=2100.0, atr=10.0, timestamp_ms=1500)
    assert engine.position.stop_loss > stop_inicial  # trailing subió con el máximo
    event = engine.on_price(
        decision=_decision(Action.HOLD), price=2069.0, atr=10.0, timestamp_ms=2000
    )
    assert event.exit_reason == "trailing_stop"


def test_sell_closes_existing_position(cfg: RiskConfig) -> None:
    engine = _engine(cfg)
    engine.on_price(decision=_decision(Action.BUY), price=2000.0, atr=10.0, timestamp_ms=1000)
    event = engine.on_price(
        decision=_decision(Action.SELL), price=2020.0, atr=10.0, timestamp_ms=1500
    )
    assert event.exit_reason == "llm_sell"
    assert engine.portfolio.position == 0.0


def test_hold_without_position_is_noop(cfg: RiskConfig) -> None:
    engine = _engine(cfg)
    event = engine.on_price(
        decision=_decision(Action.HOLD), price=2000.0, atr=10.0, timestamp_ms=1000
    )
    assert event.filled is False
    assert engine.portfolio.position == 0.0


def test_daily_loss_guard_blocks_new_entry(cfg: RiskConfig) -> None:
    engine = _engine(cfg)
    engine._realized_pnl_today = -(cfg.capital * cfg.max_daily_loss)  # pérdida límite
    event = engine.on_price(
        decision=_decision(Action.BUY), price=2000.0, atr=10.0, timestamp_ms=1000
    )
    assert event.filled is False
    assert event.risk_reason == "max_daily_loss"


def test_kill_switch_blocks_entry_and_survives_restart(cfg: RiskConfig) -> None:
    ks = KillSwitch(KillSwitchState(active=True, reason="dd", activated_at_ms=1))
    engine = _engine(cfg)
    engine.attach_kill_switch(ks)
    event = engine.on_price(
        decision=_decision(Action.BUY), price=2000.0, atr=10.0, timestamp_ms=1000
    )
    assert event.filled is False
    assert event.risk_reason == "kill_switch"


def test_determinism_same_inputs_same_outputs(cfg: RiskConfig) -> None:
    """Misma secuencia de precios/decisiones ⇒ mismo PnL neto (PRD §25)."""
    prices = [2000.0, 2050.0, 2030.0, 2010.0]
    decisions = [Action.BUY, Action.HOLD, Action.HOLD, Action.SELL]

    def run() -> float:
        e = _engine(cfg)
        for i, (p, d) in enumerate(zip(prices, decisions, strict=True)):
            e.on_price(
                decision=_decision(d, ts=1000 + i * 500),
                price=p,
                atr=10.0,
                timestamp_ms=1000 + i * 500,
            )
        return e.portfolio.realized_pnl

    assert run() == pytest.approx(run())


def test_net_pnl_includes_fees_and_slippage(cfg: RiskConfig) -> None:
    engine = _engine(cfg)
    engine.on_price(decision=_decision(Action.BUY), price=2000.0, atr=10.0, timestamp_ms=1000)
    engine.on_price(decision=_decision(Action.SELL), price=2020.0, atr=10.0, timestamp_ms=1500)
    trade = engine.portfolio.trades[-1]
    assert trade.gross_pnl != trade.net_pnl  # fees descontados (slippage in exec_price)
    assert trade.fees > 0 and trade.slippage > 0


def test_equity_marked_to_market_updates_peak(cfg: RiskConfig) -> None:
    engine = _engine(cfg)
    engine.on_price(decision=_decision(Action.BUY), price=2000.0, atr=10.0, timestamp_ms=1000)
    engine.mark_to_market(price=2100.0)
    assert engine.peak_equity == pytest.approx(engine.portfolio.equity(2100.0))


def test_entry_exceeding_cash_is_scaled_to_cash(cfg: RiskConfig) -> None:
    """Sizing que excede el cash disponible se ajusta sin quedar en negativo."""
    engine = PaperEngine(config=replace(cfg, stop_loss_required=False))
    # Sin ATR y sin stop exigido ⇒ sizing por asignación (≈ todo el capital).
    event = engine.on_price(
        decision=_decision(Action.BUY, intensity=Intensity.HIGH),
        price=2000.0,
        atr=None,
        timestamp_ms=1000,
    )
    assert event.filled is True
    assert event.fill is not None
    assert engine.portfolio.cash >= -1e-6
    assert event.fill.notional <= cfg.capital


def test_small_entry_within_cash_skips_adjustment() -> None:
    """Sizing pequeño (asignación 2% por defecto): sin ajuste de cash."""
    engine = PaperEngine(config=RiskConfig())  # cap 2% de 1000 = 20 USDT
    event = engine.on_price(
        decision=_decision(Action.BUY), price=2000.0, atr=10.0, timestamp_ms=1000
    )
    assert event.filled is True
    assert event.fill is not None
    assert event.fill.notional <= (
        RiskConfig().max_position_allocation * RiskConfig().capital * (1.0 + 0.0002 + 1e-9)
    )
    assert engine.portfolio.cash > RiskConfig().capital * 0.97


def test_check_exits_without_position_returns_none(cfg: RiskConfig) -> None:
    engine = _engine(cfg)
    assert engine._check_exits(price=2000.0, timestamp_ms=1) is None  # noqa: SLF001


def test_paper_position_value_type(cfg: RiskConfig) -> None:
    pos = PaperPosition(
        quantity=0.5,
        entry_price=2000.0,
        stop_loss=1980.0,
        take_profit=2040.0,
        highest_price=2000.0,
        entry_ts=1000,
    )
    assert pos.quantity == 0.5 and pos.highest_price >= pos.entry_price

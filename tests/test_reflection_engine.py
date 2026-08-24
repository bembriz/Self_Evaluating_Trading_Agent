"""Tests del Reflection Engine estructurado (PRD §35, Fase 11)."""

import pytest

from application.services.reflection_engine import ReflectionEngine
from domain.evaluation.outcome import TradeOutcome, TradeResult
from domain.memory.reflection import ReflectionResult
from domain.portfolio.portfolio import Trade


def _outcome(result: TradeResult, mfe: float = 20.0, mae: float = 5.0) -> TradeOutcome:
    trade = Trade(
        entry_ts=1000,
        exit_ts=2000,
        entry_price=2000.0,
        exit_price=2010.0,
        quantity=0.5,
        gross_pnl=10.0,
        fees=1.0,
        slippage=1.0,
        net_pnl=8.0 if result is TradeResult.WIN else (-8.0 if result is TradeResult.LOSS else 0.0),
    )
    return TradeOutcome(trade=trade, result=result, mfe=mfe, mae=mae, r_multiple=None)


@pytest.fixture
def engine() -> ReflectionEngine:
    return ReflectionEngine(mae_counter_trend_atr=2.5, premature_capture_ratio=0.4)


def test_loss_with_large_mae_is_counter_trend(engine: ReflectionEngine) -> None:
    r = engine.reflect(outcome=_outcome(TradeResult.LOSS, mae=30.0), atr_at_entry=10.0)
    assert r.primary_error == "COUNTER_TREND_ENTRY"
    assert r.result is ReflectionResult.LOSS
    assert r.lesson


def test_win_with_low_capture_is_premature_exit(engine: ReflectionEngine) -> None:
    r = engine.reflect(
        outcome=_outcome(TradeResult.WIN, mfe=50.0),
        atr_at_entry=None,
        captured_pnl=8.0,
    )
    assert r.primary_error == "PREMATURE_EXIT"


def test_breakeven_maps_to_no_edge(engine: ReflectionEngine) -> None:
    r = engine.reflect(outcome=_outcome(TradeResult.BREAKEVEN))
    assert r.primary_error == "NO_EDGE"


def test_clean_win_has_no_primary_error(engine: ReflectionEngine) -> None:
    r = engine.reflect(outcome=_outcome(TradeResult.WIN, mfe=12.0), captured_pnl=8.0)
    assert r.primary_error == ""
    assert r.result is ReflectionResult.WIN


def test_reflection_ids_unique_and_outcome_closed(engine: ReflectionEngine) -> None:
    a = engine.reflect(outcome=_outcome(TradeResult.WIN), closed_at_ms=100)
    b = engine.reflect(outcome=_outcome(TradeResult.WIN), closed_at_ms=200)
    assert a.id != b.id
    assert a.outcome_closed_at_ms == 100 and b.outcome_closed_at_ms == 200

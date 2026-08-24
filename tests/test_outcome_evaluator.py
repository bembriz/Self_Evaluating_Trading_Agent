"""Tests del evaluador de outcomes con MFE/MAE (PRD §46, Fase 11)."""

import pytest

from domain.evaluation.outcome import TradeOutcome, evaluate_outcome
from domain.portfolio.portfolio import Trade


def _trade(net_pnl: float, entry: float = 2000.0, exit_: float = 2010.0) -> Trade:
    return Trade(
        entry_ts=1000,
        exit_ts=2000,
        entry_price=entry,
        exit_price=exit_,
        quantity=0.5,
        gross_pnl=net_pnl + 2.0,
        fees=1.0,
        slippage=1.0,
        net_pnl=net_pnl,
    )


def test_mfe_mae_basic() -> None:
    outcome = evaluate_outcome(
        trade=_trade(10.0),
        highest_prices=[2005.0, 2020.0],
        lowest_prices=[1998.0, 2002.0],
    )
    assert isinstance(outcome, TradeOutcome)
    assert outcome.mfe == pytest.approx(20.0)  # max high − entry
    assert outcome.mae == pytest.approx(2.0)  # entry − min low
    assert outcome.result == "WIN"


def test_mae_never_negative_when_no_adverse_move() -> None:
    outcome = evaluate_outcome(
        trade=_trade(5.0),
        highest_prices=[2001.0],
        lowest_prices=[2001.5],  # nunca bajó de la entrada
    )
    assert outcome.mae == 0.0


def test_mfe_captures_entry_when_flat() -> None:
    outcome = evaluate_outcome(
        trade=_trade(-1.0),
        highest_prices=[1999.0],
        lowest_prices=[1990.0],
    )
    assert outcome.mfe == 0.0  # nunca superó la entrada
    assert outcome.mae == pytest.approx(10.0)
    assert outcome.result == "LOSS"


def test_breakeven_result(cfg: None = None) -> None:
    outcome = evaluate_outcome(
        trade=_trade(0.0),
        highest_prices=[2010.0],
        lowest_prices=[1995.0],
    )
    assert outcome.result == "BREAKEVEN"


def test_empty_paths_give_zero_excursions() -> None:
    outcome = evaluate_outcome(trade=_trade(3.0), highest_prices=[], lowest_prices=[])
    assert outcome.mfe == 0.0 and outcome.mae == 0.0


def test_r_multiple_realized() -> None:
    """Capturado vs riesgo inicial: net / (entry − stop)."""
    outcome = evaluate_outcome(
        trade=_trade(20.0),
        highest_prices=[2040.0],
        lowest_prices=[1990.0],
        initial_stop=1980.0,
    )
    risk = 2000.0 - 1980.0
    assert outcome.r_multiple == pytest.approx(20.0 / risk)

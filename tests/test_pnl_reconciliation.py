"""Tests RED — reconciliación contable y fix de slippage doble contabilizada (bug #2).

Opción A: slippage embebida en exec_price; net_pnl = gross_pnl − fees (sin re-restar
slippage). Deben FALLAR contra la implementación actual (que resta slippage 2 veces).
"""

from __future__ import annotations

import pytest

from domain.evaluation.metrics import compute_metrics
from domain.portfolio.portfolio import Portfolio
from domain.trading.fill import Fill
from domain.trading.signal import Action

TOL = 1e-9


def _buy(price: float, exec_price: float, qty: float, fee: float, slip: float, ts: int = 0) -> Fill:
    return Fill(ts, Action.BUY, price, exec_price, qty, exec_price * qty, fee, slip)


def _sell(
    price: float, exec_price: float, qty: float, fee: float, slip: float, ts: int = 1
) -> Fill:
    return Fill(ts, Action.SELL, price, exec_price, qty, exec_price * qty, fee, slip)


def _round_trip() -> Portfolio:
    p = Portfolio(initial_cash=1000.0, cash=1000.0)
    p.apply_buy(_buy(100.0, 100.5, 1.0, 0.10, 0.5))
    p.apply_sell(_sell(110.0, 109.5, 1.0, 0.11, 0.5))
    return p


def test_round_trip_manual_calculation() -> None:
    p = _round_trip()
    # gross = (109.5 - 100.5)*1 = 9.0 ; fees = 0.10 + 0.11 = 0.21 ; net = 8.79
    assert p.position == 0.0
    assert p.realized_pnl == pytest.approx(8.79, abs=TOL)
    assert p.cash == pytest.approx(1008.79, abs=TOL)


def test_equity_delta_equals_realized_pnl_when_flat() -> None:
    p = _round_trip()
    assert p.position == 0.0
    assert p.cash - 1000.0 == pytest.approx(p.realized_pnl, abs=TOL)


def test_reconciliation_residual_zero() -> None:
    p = _round_trip()
    residual = p.cash - 1000.0 - p.realized_pnl
    assert residual == pytest.approx(0.0, abs=TOL)


def test_slippage_affects_pnl_exactly_once() -> None:
    p = _round_trip()
    # gross ya incluye slippage (exec 100.5 / 109.5); net = gross - fees (sin re-restar).
    assert p.realized_pnl == pytest.approx(9.0 - 0.21, abs=TOL)


def test_fees_affect_pnl_exactly_once() -> None:
    p = _round_trip()
    assert p.realized_pnl == pytest.approx(9.0 - (0.10 + 0.11), abs=TOL)


def test_slippage_zero_reconciles() -> None:
    p = Portfolio(initial_cash=1000.0, cash=1000.0)
    p.apply_buy(_buy(100.0, 100.0, 1.0, 0.10, 0.0))
    p.apply_sell(_sell(110.0, 110.0, 1.0, 0.11, 0.0))
    assert p.realized_pnl == pytest.approx(10.0 - 0.21, abs=TOL)
    assert (p.cash - 1000.0) - p.realized_pnl == pytest.approx(0.0, abs=TOL)


def test_increasing_slippage_worsens_pnl_without_double_count() -> None:
    low = Portfolio(initial_cash=1000.0, cash=1000.0)
    low.apply_buy(_buy(100.0, 100.0, 1.0, 0.0, 0.0))
    low.apply_sell(_sell(110.0, 110.0, 1.0, 0.0, 0.0))
    high = Portfolio(initial_cash=1000.0, cash=1000.0)
    high.apply_buy(_buy(100.0, 101.0, 1.0, 0.0, 0.0))
    high.apply_sell(_sell(110.0, 109.0, 1.0, 0.0, 0.0))

    assert low.realized_pnl == pytest.approx(10.0, abs=TOL)
    assert high.realized_pnl == pytest.approx(8.0, abs=TOL)
    # La slippage empeora el PnL exactamente el cambio de gross (una sola vez).
    assert high.realized_pnl - low.realized_pnl == pytest.approx(8.0 - 10.0, abs=TOL)
    assert (low.cash - 1000.0) - low.realized_pnl == pytest.approx(0.0, abs=TOL)
    assert (high.cash - 1000.0) - high.realized_pnl == pytest.approx(0.0, abs=TOL)


def test_entry_and_exit_slippage_included_via_exec_price() -> None:
    p = _round_trip()
    t = p.trades[0]
    # entry slippage en avg_entry (100.5), exit slippage en exec (109.5)
    assert t.gross_pnl == pytest.approx((109.5 - 100.5) * 1.0, abs=TOL)
    assert t.slippage == pytest.approx(0.5 + 0.5, abs=TOL)  # analítica, informativa
    assert t.net_pnl == pytest.approx(t.gross_pnl - t.fees, abs=TOL)


def test_compute_metrics_matches_portfolio_accounting() -> None:
    p = _round_trip()
    m = compute_metrics(p.trades, [1000.0, p.cash], periods_per_year=8760)
    assert m.net_pnl == pytest.approx(p.realized_pnl, abs=TOL)
    assert m.fees == pytest.approx(p.total_fees, abs=TOL)
    assert m.slippage == pytest.approx(p.total_slippage, abs=TOL)
    assert m.gross_pnl == pytest.approx(sum(t.gross_pnl for t in p.trades), abs=TOL)

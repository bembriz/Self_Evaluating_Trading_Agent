"""Permanent accounting regression tests — Phase 21R-B.

Proves independently that:
- exec_price embeds slippage
- Trade.net_pnl == gross_exec_pnl - fees (slippage NOT subtracted twice)
- reference view reconciles with execution view
- cash delta reconciles to realized PnL
- PerformanceMetrics.net_pnl matches corrected trade accounting
- multi-trade aggregate reconciliation residual ≈ 0
"""

import pytest

from domain.evaluation.metrics import compute_metrics
from domain.portfolio.portfolio import Portfolio
from domain.trading.fill import FillModel
from domain.trading.slippage import SlippageModel

# ---------------------------------------------------------------------------
# A1. exec_price embeds slippage
# ---------------------------------------------------------------------------


def test_buy_exec_price_includes_slippage() -> None:
    """BUY exec_price == reference_price * (1 + slippage_rate)."""
    slippage_bps = 10.0  # 10 bps
    model = FillModel(slippage_model=SlippageModel(bps=slippage_bps))
    fill = model.buy(timestamp_ms=1, price=100.0, cash=1000.0)
    expected = 100.0 * (1.0 + slippage_bps / 10_000)
    assert fill.exec_price == pytest.approx(expected)
    assert fill.exec_price > fill.price  # BUY: exec > ref


def test_sell_exec_price_includes_slippage() -> None:
    """SELL exec_price == reference_price * (1 - slippage_rate)."""
    slippage_bps = 10.0
    model = FillModel(slippage_model=SlippageModel(bps=slippage_bps))
    fill = model.sell(timestamp_ms=1, price=100.0, quantity=1.0)
    expected = 100.0 * (1.0 - slippage_bps / 10_000)
    assert fill.exec_price == pytest.approx(expected)
    assert fill.exec_price < fill.price  # SELL: exec < ref


# ---------------------------------------------------------------------------
# A2. Trade.net_pnl == gross_exec_pnl - fees
# ---------------------------------------------------------------------------


def test_trade_net_pnl_is_gross_minus_fees() -> None:
    """net_pnl must equal (exit_exec - entry_exec) * qty - total_fees."""
    p = Portfolio(initial_cash=1000.0, cash=1000.0)
    buy = FillModel().buy(timestamp_ms=1, price=100.0, cash=1000.0)
    p.apply_buy(buy)
    sell = FillModel().sell(timestamp_ms=2, price=110.0, quantity=p.position)
    p.apply_sell(sell)

    trade = p.trades[0]
    expected_gross = (sell.exec_price - buy.exec_price) * trade.quantity
    expected_net = expected_gross - trade.fees
    assert trade.gross_pnl == pytest.approx(expected_gross)
    assert trade.net_pnl == pytest.approx(expected_net)


# ---------------------------------------------------------------------------
# A3. slippage is NOT subtracted twice
# ---------------------------------------------------------------------------


def test_slippage_not_double_subtracted() -> None:
    """net_pnl must NOT subtract slippage a second time.

    slippage is already embedded in exec_price (and therefore in gross_pnl).
    net_pnl = gross_pnl - fees ONLY.
    """
    p = Portfolio(initial_cash=1000.0, cash=1000.0)
    buy = FillModel().buy(timestamp_ms=1, price=100.0, cash=1000.0)
    p.apply_buy(buy)
    sell = FillModel().sell(timestamp_ms=2, price=110.0, quantity=p.position)
    p.apply_sell(sell)

    trade = p.trades[0]
    # The WRONG formula was: net_pnl = gross_pnl - fees - slippage
    wrong_net = trade.gross_pnl - trade.fees - trade.slippage
    # The CORRECT formula is: net_pnl = gross_pnl - fees
    correct_net = trade.gross_pnl - trade.fees

    assert trade.net_pnl == pytest.approx(correct_net)
    assert trade.net_pnl != pytest.approx(wrong_net), "net_pnl must NOT double-subtract slippage"


# ---------------------------------------------------------------------------
# A4. reference view reconciles with execution view
# ---------------------------------------------------------------------------


def test_reference_view_reconciles_with_exec_view() -> None:
    """gross_ref - analytical_slippage - fees == gross_exec - fees."""
    p = Portfolio(initial_cash=1000.0, cash=1000.0)
    buy = FillModel().buy(timestamp_ms=1, price=100.0, cash=1000.0)
    p.apply_buy(buy)
    sell = FillModel().sell(timestamp_ms=2, price=110.0, quantity=p.position)
    p.apply_sell(sell)

    trade = p.trades[0]
    # Reference-price gross (no slippage)
    gross_ref = (110.0 - 100.0) * trade.quantity
    # Analytical slippage = gross_ref - gross_exec
    analytical_slippage = gross_ref - trade.gross_pnl

    net_from_ref = gross_ref - analytical_slippage - trade.fees
    net_from_exec = trade.gross_pnl - trade.fees

    assert net_from_ref == pytest.approx(net_from_exec)
    assert trade.net_pnl == pytest.approx(net_from_exec)


# ---------------------------------------------------------------------------
# A5. cash delta reconciles to realized PnL
# ---------------------------------------------------------------------------


def test_cash_delta_reconciles_to_realized_pnl() -> None:
    """cash_after_exit - cash_before_entry == trade.net_pnl (adjusted for notional flow)."""
    p = Portfolio(initial_cash=1000.0, cash=1000.0)
    cash_before = p.cash
    buy = FillModel().buy(timestamp_ms=1, price=100.0, cash=1000.0)
    p.apply_buy(buy)
    sell = FillModel().sell(timestamp_ms=2, price=110.0, quantity=p.position)
    p.apply_sell(sell)
    cash_after = p.cash

    trade = p.trades[0]
    # Cash delta = cash_after - cash_before
    # This includes: -entry_notional - entry_fee + exit_notional - exit_fee
    cash_delta = cash_after - cash_before
    # The realized PnL contribution to cash is exactly net_pnl
    assert cash_delta == pytest.approx(trade.net_pnl)


# ---------------------------------------------------------------------------
# A6. PerformanceMetrics.net_pnl matches corrected trade accounting
# ---------------------------------------------------------------------------


def test_metrics_net_pnl_matches_trade_accounting() -> None:
    """PerformanceMetrics.net_pnl must equal sum of Trade.net_pnl (corrected)."""
    p = Portfolio(initial_cash=1000.0, cash=1000.0)
    buy = FillModel().buy(timestamp_ms=1, price=100.0, cash=1000.0)
    p.apply_buy(buy)
    sell = FillModel().sell(timestamp_ms=2, price=110.0, quantity=p.position)
    p.apply_sell(sell)

    trade = p.trades[0]
    equity_curve = [1000.0, p.equity(sell.exec_price)]
    metrics = compute_metrics(p.trades, equity_curve, periods_per_year=8760, llm_cost=0.0)

    assert metrics.net_pnl == pytest.approx(trade.net_pnl)
    assert metrics.gross_pnl == pytest.approx(trade.gross_pnl)
    assert metrics.fees == pytest.approx(trade.fees)


# ---------------------------------------------------------------------------
# A7. multi-trade aggregate reconciliation residual ≈ 0
# ---------------------------------------------------------------------------


def test_multi_trade_aggregate_reconciliation() -> None:
    """Sum of individual trade net_pnl must equal portfolio realized_pnl."""
    p = Portfolio(initial_cash=1000.0, cash=1000.0)

    # Trade 1: profit
    buy1 = FillModel().buy(timestamp_ms=1, price=100.0, cash=p.cash)
    p.apply_buy(buy1)
    sell1 = FillModel().sell(timestamp_ms=2, price=110.0, quantity=p.position)
    p.apply_sell(sell1)

    # Trade 2: loss
    buy2 = FillModel().buy(timestamp_ms=3, price=110.0, cash=p.cash)
    p.apply_buy(buy2)
    sell2 = FillModel().sell(timestamp_ms=4, price=105.0, quantity=p.position)
    p.apply_sell(sell2)

    # Trade 3: profit
    buy3 = FillModel().buy(timestamp_ms=5, price=105.0, cash=p.cash)
    p.apply_buy(buy3)
    sell3 = FillModel().sell(timestamp_ms=6, price=115.0, quantity=p.position)
    p.apply_sell(sell3)

    total_trade_net = sum(t.net_pnl for t in p.trades)
    assert p.realized_pnl == pytest.approx(total_trade_net)

    # Also verify with metrics
    equity_curve = [1000.0]
    for t in p.trades:
        equity_curve.append(equity_curve[-1] + t.net_pnl)
    metrics = compute_metrics(p.trades, equity_curve, periods_per_year=8760)
    assert metrics.net_pnl == pytest.approx(total_trade_net)

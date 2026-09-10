import pytest

from domain.portfolio.portfolio import Portfolio
from domain.trading.fill import FillModel


def test_buy_increases_position_and_reduces_cash() -> None:
    p = Portfolio(initial_cash=1000.0, cash=1000.0)
    fill = FillModel().buy(timestamp_ms=1, price=100.0, cash=1000.0)
    p.apply_buy(fill)
    assert p.position == pytest.approx(fill.quantity)
    assert p.cash == pytest.approx(1000.0 - fill.notional - fill.fee)
    assert p.avg_entry == pytest.approx(fill.exec_price)


def test_sell_reduces_position_and_records_trade() -> None:
    p = Portfolio(initial_cash=1000.0, cash=1000.0)
    buy = FillModel().buy(timestamp_ms=1, price=100.0, cash=1000.0)
    p.apply_buy(buy)
    sell = FillModel().sell(timestamp_ms=2, price=110.0, quantity=p.position)
    p.apply_sell(sell)
    assert p.position == 0.0
    assert len(p.trades) == 1
    trade = p.trades[0]
    assert trade.quantity == pytest.approx(buy.quantity)
    assert trade.gross_pnl > 0
    assert trade.net_pnl == pytest.approx(trade.gross_pnl - trade.fees)


def test_sell_cannot_short() -> None:
    p = Portfolio(initial_cash=1000.0, cash=1000.0)
    p.apply_buy(FillModel().buy(timestamp_ms=1, price=100.0, cash=1000.0))
    qty = p.position
    p.apply_sell(FillModel().sell(timestamp_ms=2, price=100.0, quantity=qty * 2))
    assert p.position == 0.0
    assert len(p.trades) == 1


def test_sell_without_position_is_ignored() -> None:
    p = Portfolio(initial_cash=1000.0, cash=1000.0)
    p.apply_sell(FillModel().sell(timestamp_ms=2, price=100.0, quantity=5.0))
    assert p.position == 0.0
    assert p.trades == []
    assert p.cash == pytest.approx(1000.0)


def test_buy_exceeding_cash_raises() -> None:
    p = Portfolio(initial_cash=100.0, cash=100.0)
    fake = FillModel().buy(timestamp_ms=1, price=100.0, cash=1000.0)
    with pytest.raises(ValueError):
        p.apply_buy(fake)


def test_equity_is_cash_plus_position_value() -> None:
    p = Portfolio(initial_cash=1000.0, cash=1000.0)
    p.apply_buy(FillModel().buy(timestamp_ms=1, price=100.0, cash=1000.0))
    assert p.equity(120.0) == pytest.approx(p.cash + p.position * 120.0)


def test_weighted_average_entry() -> None:
    p = Portfolio(initial_cash=1000.0, cash=1000.0)
    p.apply_buy(FillModel().buy(timestamp_ms=1, price=100.0, cash=500.0))
    p.apply_buy(FillModel().buy(timestamp_ms=2, price=200.0, cash=p.cash))
    assert p.avg_entry is not None
    assert 100.0 < p.avg_entry < 200.0


def test_buy_empty_fill_is_ignored() -> None:
    p = Portfolio(initial_cash=1000.0, cash=1000.0)
    empty = FillModel().buy(timestamp_ms=1, price=100.0, cash=0.0)
    p.apply_buy(empty)
    assert p.position == 0.0
    assert p.cash == pytest.approx(1000.0)


def test_partial_sell_keeps_position() -> None:
    p = Portfolio(initial_cash=1000.0, cash=1000.0)
    p.apply_buy(FillModel().buy(timestamp_ms=1, price=100.0, cash=1000.0))
    qty = p.position
    p.apply_sell(FillModel().sell(timestamp_ms=2, price=110.0, quantity=qty / 2))
    assert p.position > 0
    assert p.avg_entry is not None
    assert len(p.trades) == 1

import pytest

from domain.trading.fees import FeeModel
from domain.trading.fill import FillModel
from domain.trading.signal import Action
from domain.trading.slippage import SlippageModel


def test_fee_is_notional_times_rate() -> None:
    fee = FeeModel(taker_bps=10.0)
    assert fee.taker_rate == pytest.approx(0.001)
    assert fee.fee(1000.0) == pytest.approx(1.0)


def test_slippage_cost() -> None:
    slip = SlippageModel(bps=2.0)
    assert slip.cost(1000.0) == pytest.approx(0.2)


def test_buy_spends_cash_including_fee() -> None:
    fill = FillModel().buy(timestamp_ms=1, price=100.0, cash=1000.0)
    assert fill.action is Action.BUY
    assert fill.exec_price == pytest.approx(100.0 * 1.0002)
    # notional + fee == cash
    assert fill.notional + fill.fee == pytest.approx(1000.0)
    assert fill.quantity > 0


def test_buy_zero_cash_returns_empty_fill() -> None:
    fill = FillModel().buy(timestamp_ms=1, price=100.0, cash=0.0)
    assert fill.quantity == 0.0
    assert fill.notional == 0.0
    assert fill.fee == 0.0


def test_sell_applies_negative_slippage() -> None:
    fill = FillModel().sell(timestamp_ms=2, price=100.0, quantity=10.0)
    assert fill.action is Action.SELL
    assert fill.exec_price == pytest.approx(100.0 * (1.0 - 0.0002))
    assert fill.notional == pytest.approx(10.0 * fill.exec_price)
    assert fill.fee == pytest.approx(fill.notional * 0.001)
    assert fill.slippage_cost > 0


def test_sell_zero_quantity_returns_empty_fill() -> None:
    fill = FillModel().sell(timestamp_ms=2, price=100.0, quantity=0.0)
    assert fill.quantity == 0.0
    assert fill.notional == 0.0


def test_custom_models_are_used() -> None:
    fee = FeeModel(taker_bps=20.0)
    slip = SlippageModel(bps=5.0)
    fill = FillModel(fee_model=fee, slippage_model=slip).buy(1, 100.0, 1000.0)
    assert fill.exec_price == pytest.approx(100.0 * 1.0005)
    assert fill.fee == pytest.approx(fill.notional * 0.002)

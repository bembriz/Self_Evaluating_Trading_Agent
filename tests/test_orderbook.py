import pytest

from domain.market.orderbook import OrderBook, OrderBookDesync, OrderBookLevel

SNAP_BIDS = [OrderBookLevel(100.0, 1.0), OrderBookLevel(99.0, 2.0)]
SNAP_ASKS = [OrderBookLevel(101.0, 1.5), OrderBookLevel(102.0, 3.0)]


def test_snapshot_and_quotes() -> None:
    ob = OrderBook("ETHUSDT")
    ob.apply_snapshot(SNAP_BIDS, SNAP_ASKS, update_id=10)
    assert ob.best_bid == 100.0
    assert ob.best_ask == 101.0
    assert ob.mid == 100.5
    assert ob.spread == 1.0


def test_delta_updates_and_deletes() -> None:
    ob = OrderBook("ETHUSDT")
    ob.apply_snapshot(SNAP_BIDS, SNAP_ASKS, update_id=10)
    ob.apply_delta(
        [OrderBookLevel(100.0, 0.0), OrderBookLevel(99.5, 2.5)],
        [OrderBookLevel(101.0, 0.0)],
        update_id=11,
    )
    assert ob.best_bid == 99.5
    assert ob.best_ask == 102.0


def test_delta_gap_raises_desync() -> None:
    ob = OrderBook("ETHUSDT")
    ob.apply_snapshot(SNAP_BIDS, SNAP_ASKS, update_id=10)
    with pytest.raises(OrderBookDesync):
        ob.apply_delta([], [], update_id=13)


def test_delta_out_of_order_ignored() -> None:
    ob = OrderBook("ETHUSDT")
    ob.apply_snapshot(SNAP_BIDS, SNAP_ASKS, update_id=10)
    ob.apply_delta([OrderBookLevel(100.5, 2.5)], [], update_id=11)
    ob.apply_delta([OrderBookLevel(100.6, 1.0)], [], update_id=10)  # <= last → ignorado
    assert ob.best_bid == 100.5


def test_depth_and_imbalance() -> None:
    ob = OrderBook("ETHUSDT")
    ob.apply_snapshot(
        [OrderBookLevel(100.0, 1.0), OrderBookLevel(99.0, 2.0)],
        [OrderBookLevel(101.0, 1.5), OrderBookLevel(102.0, 3.0)],
        update_id=1,
    )
    assert ob.depth("bids", 2) == 3.0
    assert ob.depth("asks", 2) == 4.5
    assert ob.imbalance == pytest.approx(3.0 / (3.0 + 4.5))


def test_is_healthy() -> None:
    ob = OrderBook("ETHUSDT")
    assert ob.is_healthy is False
    ob.apply_snapshot(SNAP_BIDS, SNAP_ASKS, update_id=1)
    assert ob.is_healthy is True

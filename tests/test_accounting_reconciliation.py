"""Unit tests for accounting_reconciliation (mirror kernel + three-way checkpoint)."""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from typing import Any

import pytest

from application.ports.paper_trading import PaperTradeEvent
from application.services.accounting_reconciliation import (
    AccountingLedger,
    BookState,
    MissingMarkError,
    _advance,
    _apply_buy,
    _apply_sell,
    _book_from_ledger,
    _compare,
    _cursor_from_value,
    _d,
    _ledger_from_state,
    _mirror_start,
    latest_persisted_mark,
    reconcile_accounting,
    reconcile_with_book,
    residual,
)
from domain.market.candle import Candle

INITIAL = 1000.0


def _event(**overrides: Any) -> PaperTradeEvent:
    base: dict[str, Any] = {
        "session_id": "sess-1",
        "strategy_version": "baseline-v1",
        "strategy_hash": "h" * 32,
        "decision_source": "baseline",
        "symbol": "ETHUSDT",
        "timeframe": "15m",
        "timestamp_ms": 0,
        "action": "HOLD",
        "filled": False,
        "risk_reason": "",
        "exit_reason": "",
        "exec_price": None,
        "quantity": None,
        "fee": 0.0,
        "slippage_cost": 0.0,
        "equity": INITIAL,
        "kill_switch_active": False,
    }
    base.update(overrides)
    return PaperTradeEvent(**base)


def _round_trip() -> list[PaperTradeEvent]:
    buy = _event(
        timestamp_ms=1,
        action="BUY",
        filled=True,
        exec_price=100.0,
        quantity=1.0,
        fee=0.1,
        slippage_cost=0.01,
        equity=999.9,
    )
    sell = _event(
        timestamp_ms=2,
        action="SELL",
        filled=True,
        exit_reason="take_profit",
        exec_price=110.0,
        quantity=1.0,
        fee=0.11,
        slippage_cost=0.02,
        equity=1009.79,
    )
    return [buy, sell]


def test_d_and_latest_mark() -> None:
    assert _d(0.1) == Decimal("0.1")
    assert latest_persisted_mark([]) is None
    candle = Candle(timestamp_ms=0, open=1, high=2, low=0.5, close=1.5, volume=1, turnover=1)
    assert latest_persisted_mark([candle]) == 1.5


def test_mirror_start_shape() -> None:
    assert _mirror_start(500.0) == (500.0, 0.0, None, 0.0, 0.0, 0.0, 0.0, 0.0)


def test_advance_ignores_non_fills_and_holds() -> None:
    events = [
        _event(action="HOLD", filled=False),
        _event(action="BUY", filled=False),
        _event(action="SELL", filled=False),
        _event(action="BUY", filled=True, exec_price=None, quantity=1.0),
    ]
    assert _advance(_mirror_start(INITIAL), events) == _mirror_start(INITIAL)


def test_ledger_requires_mark_when_position_open() -> None:
    open_state = _apply_buy(
        cash=INITIAL,
        position=0.0,
        avg_entry=None,
        entry_fees=0.0,
        entry_slippage=0.0,
        total_fees=0.0,
        total_slippage=0.0,
        exec_price=100.0,
        quantity=1.0,
        fee=0.0,
        slippage_cost=0.0,
    )
    cash, position, avg_entry, ef, es, tf, ts = open_state
    state = (cash, position, avg_entry, ef, es, 0.0, tf, ts)
    with pytest.raises(MissingMarkError):
        _ledger_from_state(state, mark_price=None)
    ledger = _ledger_from_state(state, mark_price=105.0)
    assert ledger.reconstructed_equity == Decimal("1005")


def test_reconcile_accounting_round_trip() -> None:
    ledger = reconcile_accounting(
        _round_trip(), initial_capital=INITIAL, mark_price=None, interval_ms=900_000
    )
    assert ledger.cash == Decimal("1009.79")
    assert ledger.position_qty == Decimal("0")
    assert ledger.realized_pnl == Decimal("9.79")
    assert float(ledger.fees) == pytest.approx(0.21)
    assert ledger.reconstructed_equity == Decimal("1009.79")


def test_apply_buy_zero_qty_and_averaging() -> None:
    unchanged = _apply_buy(
        cash=100.0,
        position=0.0,
        avg_entry=None,
        entry_fees=0.0,
        entry_slippage=0.0,
        total_fees=0.0,
        total_slippage=0.0,
        exec_price=10.0,
        quantity=0.0,
        fee=0.0,
        slippage_cost=0.0,
    )
    assert unchanged == (100.0, 0.0, None, 0.0, 0.0, 0.0, 0.0)
    averaged = _apply_buy(
        cash=100.0,
        position=1.0,
        avg_entry=10.0,
        entry_fees=0.0,
        entry_slippage=0.0,
        total_fees=0.0,
        total_slippage=0.0,
        exec_price=20.0,
        quantity=1.0,
        fee=0.5,
        slippage_cost=0.05,
    )
    assert averaged[0] == 100.0 - (20.0 + 0.5)
    assert averaged[1] == 2.0
    assert averaged[2] == pytest.approx(15.0)
    assert averaged[5] == 0.5


def test_apply_sell_noop_and_partial() -> None:
    noop = _apply_sell(
        cash=100.0,
        position=1.0,
        avg_entry=10.0,
        entry_fees=0.1,
        entry_slippage=0.01,
        realized_pnl=0.0,
        total_fees=0.1,
        total_slippage=0.01,
        exec_price=20.0,
        quantity=0.0,
        fee=0.0,
        slippage_cost=0.0,
    )
    assert noop == (100.0, 1.0, 10.0, 0.1, 0.01, 0.0, 0.1, 0.01)
    partial = _apply_sell(
        cash=100.0,
        position=2.0,
        avg_entry=10.0,
        entry_fees=0.2,
        entry_slippage=0.02,
        realized_pnl=0.0,
        total_fees=0.2,
        total_slippage=0.02,
        exec_price=20.0,
        quantity=1.0,
        fee=0.1,
        slippage_cost=0.01,
    )
    assert partial[1] == 1.0
    assert partial[2] == 10.0
    assert partial[5] == pytest.approx(10.0 - 0.1 - 0.1)


def test_apply_sell_full_close_resets_position() -> None:
    closed = _apply_sell(
        cash=100.0,
        position=1.0,
        avg_entry=10.0,
        entry_fees=0.1,
        entry_slippage=0.0,
        realized_pnl=0.0,
        total_fees=0.1,
        total_slippage=0.0,
        exec_price=12.0,
        quantity=1.0,
        fee=0.1,
        slippage_cost=0.0,
    )
    assert closed[1] == 0.0
    assert closed[2] is None


def test_residual_exact() -> None:
    ledger = AccountingLedger(
        cash=Decimal("1000"),
        position_qty=Decimal("0"),
        average_entry=Decimal("0"),
        realized_pnl=Decimal("0"),
        fees=Decimal("0"),
        reconstructed_equity=Decimal("1000"),
    )
    assert residual(1000.0, ledger) == Decimal("0")
    assert residual(1000.5, ledger) == Decimal("0.5")


def test_book_state_round_trip() -> None:
    book = BookState(
        cash=Decimal("1000"),
        position_qty=Decimal("0"),
        average_entry=None,
        realized_pnl=Decimal("5"),
        fees=Decimal("0.2"),
        equity=Decimal("1005"),
        entry_fees=Decimal("0.2"),
        last_event_ms=42,
    )
    payload = book.to_dict()
    assert payload["average_entry"] == ""
    restored = BookState.from_dict(payload)
    assert restored == book


def test_book_state_from_dict_missing_and_bad() -> None:
    assert BookState.from_dict({}) is None
    assert BookState.from_dict({**_required(), "cash": "not-a-number"}) is None
    legacy = {**_required(), "last_event_ms": "nope"}
    parsed = BookState.from_dict(legacy)
    assert parsed is not None and parsed.last_event_ms is None


def _required() -> dict[str, Any]:
    return {
        "cash": "1000",
        "position_qty": "0",
        "realized_pnl": "0",
        "fees": "0",
        "equity": "1000",
    }


def test_cursor_from_value() -> None:
    assert _cursor_from_value(None) is None
    assert _cursor_from_value("") is None
    assert _cursor_from_value(True) is None
    assert _cursor_from_value(7) == 7
    assert _cursor_from_value("8") == 8
    assert _cursor_from_value("x") is None
    assert _cursor_from_value(1.5) is None


def test_book_from_ledger_and_compare() -> None:
    ledger = AccountingLedger(
        cash=Decimal("1000"),
        position_qty=Decimal("0"),
        average_entry=Decimal("0"),
        realized_pnl=Decimal("0"),
        fees=Decimal("0"),
        reconstructed_equity=Decimal("1000"),
    )
    book = _book_from_ledger(ledger, entry_fees=0.0, last_event_ms=9)
    assert book.average_entry is None
    assert book.last_event_ms == 9
    mismatches: list[str] = []
    deltas: list[Decimal] = []
    _compare(mismatches, deltas, "cash", Decimal("1"), Decimal("2"))
    assert mismatches == ["cash"]
    assert deltas == [Decimal("1")]
    _compare(mismatches, deltas, "fees", Decimal("3"), Decimal("3"))
    assert mismatches == ["cash"]


def test_reconcile_with_book_baseline_then_pass() -> None:
    events = _round_trip()
    baseline = reconcile_with_book(
        events,
        initial_capital=INITIAL,
        mark_price=None,
        previous_book=None,
        interval_ms=900_000,
    )
    assert baseline.status == "PASS"
    assert baseline.accounting_residual == Decimal("0")
    assert baseline.book.last_event_ms == 2

    resumed = reconcile_with_book(
        events,
        initial_capital=INITIAL,
        mark_price=None,
        previous_book=baseline.book.to_dict(),
        interval_ms=900_000,
    )
    assert resumed.status == "PASS"
    assert resumed.mismatches == ()


def test_reconcile_with_book_fails_on_live_equity_drift() -> None:
    events = _round_trip()
    baseline = reconcile_with_book(
        events,
        initial_capital=INITIAL,
        mark_price=None,
        previous_book=None,
        interval_ms=900_000,
    )
    corrupted = [events[0], dataclasses.replace(events[1], equity=1234.0)]
    result = reconcile_with_book(
        corrupted,
        initial_capital=INITIAL,
        mark_price=None,
        previous_book=baseline.book.to_dict(),
        interval_ms=900_000,
    )
    assert result.status == "FAIL"
    assert "equity" in result.mismatches
    assert result.accounting_residual > Decimal("0")


def test_reconcile_with_book_baseline_when_cursor_missing() -> None:
    events = _round_trip()
    without_cursor = _required()
    result = reconcile_with_book(
        events,
        initial_capital=INITIAL,
        mark_price=None,
        previous_book=without_cursor,
        interval_ms=900_000,
    )
    assert result.status == "PASS"
    assert result.book.last_event_ms == 2

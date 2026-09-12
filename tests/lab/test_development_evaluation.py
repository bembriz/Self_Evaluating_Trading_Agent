"""Phase 18B unit contract for the pure DEVELOPMENT evaluation helpers."""

from __future__ import annotations

from types import MappingProxyType

import pytest

from domain.trading.signal import Action, Signal
from lab.development_evaluation import (
    MAX_DRAWDOWN_MATERIAL_ABS,
    btc_filter_attribution,
    classify_development_result,
    compare_metrics,
    count_signals,
    session_metrics,
)
from lab.session_runner import LabCandleEvent, LabSessionResult

SPEC_ID = "ab" * 32


def _event(
    ts: int,
    action: str,
    filled: bool,
    *,
    price: float | None = None,
    qty: float = 0.2,
    fee: float = 0.0,
    slip: float = 0.0,
    equity: float = 1000.0,
) -> LabCandleEvent:
    return LabCandleEvent(
        timestamp_ms=ts,
        action=action,
        filled=filled,
        exit_reason="",
        risk_reason="",
        exec_price=price,
        quantity=qty if filled else None,
        fee=fee,
        slippage_cost=slip,
        equity=equity,
    )


def _result(events: tuple[LabCandleEvent, ...], *, initial: float = 1000.0) -> LabSessionResult:
    return LabSessionResult(
        experiment_spec_id=SPEC_ID,
        events=events,
        metrics=MappingProxyType({"equity_initial": initial}),
        event_trace_hash="cd" * 32,
        metrics_hash_value="ef" * 32,
    )


def _round_trip(
    entry_ts: int, exit_ts: int, *, entry: float, exit: float, fee: float, slip: float
) -> tuple[LabCandleEvent, LabCandleEvent]:
    return (
        _event(entry_ts, "BUY", True, price=entry, fee=fee, slip=slip),
        _event(exit_ts, "SELL", True, price=exit, fee=fee, slip=slip),
    )


def test_count_signals_splits_buy_sell_hold() -> None:
    signals = (
        Signal(1, Action.BUY),
        Signal(2, Action.SELL),
        Signal(3, Action.HOLD),
        Signal(4, Action.BUY),
    )
    assert count_signals(signals) == {"signals_buy": 2, "signals_sell": 1, "signals_hold": 1}


def test_session_metrics_uses_existing_formulas() -> None:
    events = (
        *_round_trip(1, 2, entry=100.0, exit=110.0, fee=0.02, slip=0.004),
        *_round_trip(3, 4, entry=100.0, exit=90.0, fee=0.02, slip=0.004),
    )
    metrics = session_metrics(_result(events))
    assert metrics["closed_trades"] == 2
    assert metrics["fills"] == 4
    assert metrics["fees"] == pytest.approx(0.08)
    assert metrics["slippage"] == pytest.approx(0.016)
    assert metrics["net_pnl"] == pytest.approx(1.952 - 2.048)
    assert metrics["return_pct"] == pytest.approx(metrics["net_pnl"] / 1000.0)
    assert metrics["win_rate"] == pytest.approx(0.5)
    assert metrics["average_win"] == pytest.approx(1.952)
    assert metrics["average_loss"] == pytest.approx(-2.048)
    assert metrics["profit_factor"] == pytest.approx(1.952 / 2.048)
    assert metrics["expectancy"] == pytest.approx(metrics["net_pnl"] / 2)
    assert metrics["max_drawdown"] >= 0.0


def test_session_metrics_zero_initial_equity_is_flat_return() -> None:
    metrics = session_metrics(_result((), initial=0.0))
    assert metrics["closed_trades"] == 0
    assert metrics["return_pct"] == 0.0
    assert metrics["profit_factor"] is None
    assert metrics["expectancy"] is None
    assert metrics["average_win"] is None
    assert metrics["average_loss"] is None


def _metrics(
    *,
    trades: int,
    net: float,
    ret: float,
    dd: float,
    pf: float | None,
    exp: float | None,
    fees: float = 1.0,
    slip: float = 0.5,
) -> dict[str, object]:
    return {
        "closed_trades": trades,
        "net_pnl": net,
        "return_pct": ret,
        "max_drawdown": dd,
        "profit_factor": pf,
        "expectancy": exp,
        "fees": fees,
        "slippage": slip,
    }


def test_compare_metrics_reports_all_deltas() -> None:
    baseline = _metrics(trades=4, net=10.0, ret=0.01, dd=0.05, pf=2.0, exp=2.5)
    candidate = _metrics(trades=3, net=12.0, ret=0.012, dd=0.04, pf=2.4, exp=4.0, fees=0.8)
    delta = compare_metrics(baseline, candidate)
    assert delta["delta_net_pnl"] == pytest.approx(2.0)
    assert delta["delta_return_pct"] == pytest.approx(0.002)
    assert delta["delta_max_drawdown"] == pytest.approx(-0.01)
    assert delta["delta_profit_factor"] == pytest.approx(0.4)
    assert delta["delta_expectancy"] == pytest.approx(1.5)
    assert delta["delta_trades"] == -1
    assert delta["delta_fees"] == pytest.approx(-0.2)
    assert delta["delta_slippage"] == pytest.approx(0.0)
    assert delta["trade_reduction_percent"] == pytest.approx(25.0)


def test_compare_metrics_handles_zero_trades_and_undefined_values() -> None:
    baseline = _metrics(trades=0, net=0.0, ret=0.0, dd=0.0, pf=None, exp=None)
    candidate = _metrics(trades=0, net=0.0, ret=0.0, dd=0.0, pf=float("inf"), exp=1.0)
    delta = compare_metrics(baseline, candidate)
    assert delta["trade_reduction_percent"] == 0.0
    assert delta["delta_profit_factor"] is None
    assert delta["delta_expectancy"] is None


def test_classify_improved_requires_all_and_bounded_drawdown() -> None:
    base = _metrics(trades=4, net=5.0, ret=0.005, dd=0.10, pf=1.5, exp=1.0)
    cand = _metrics(trades=3, net=8.0, ret=0.008, dd=0.10, pf=2.0, exp=2.0)
    assert classify_development_result(base, cand) == "IMPROVED"


def test_classify_not_improved_when_no_metric_improves() -> None:
    base = _metrics(trades=4, net=5.0, ret=0.005, dd=0.10, pf=1.5, exp=1.0)
    cand = _metrics(trades=2, net=4.0, ret=0.004, dd=0.10, pf=1.4, exp=0.9)
    assert classify_development_result(base, cand) == "NOT_IMPROVED"


def test_classify_not_improved_when_two_metrics_deteriorate() -> None:
    base = _metrics(trades=4, net=5.0, ret=0.005, dd=0.10, pf=1.5, exp=1.0)
    cand = _metrics(trades=3, net=6.0, ret=0.006, dd=0.10, pf=1.2, exp=0.8)
    assert classify_development_result(base, cand) == "NOT_IMPROVED"


def test_classify_mixed_partial_improvement() -> None:
    base = _metrics(trades=4, net=5.0, ret=0.005, dd=0.10, pf=1.5, exp=1.0)
    cand = _metrics(trades=3, net=5.0, ret=0.005, dd=0.10, pf=1.5, exp=2.0)
    assert classify_development_result(base, cand) == "MIXED"


def test_classify_mixed_when_drawdown_materially_worse() -> None:
    base = _metrics(trades=4, net=5.0, ret=0.005, dd=0.10, pf=1.5, exp=1.0)
    cand = _metrics(
        trades=3,
        net=8.0,
        ret=0.008,
        dd=0.10 + MAX_DRAWDOWN_MATERIAL_ABS + 0.001,
        pf=2.0,
        exp=2.0,
    )
    assert classify_development_result(base, cand) == "MIXED"


def test_classify_treats_undefined_as_neutral() -> None:
    base = _metrics(trades=2, net=5.0, ret=0.005, dd=0.10, pf=None, exp=None)
    cand = _metrics(trades=2, net=5.0, ret=0.005, dd=0.10, pf=2.0, exp=2.0)
    assert classify_development_result(base, cand) == "NOT_IMPROVED"


def test_btc_filter_attribution_accounts_and_explains_blocked_buys() -> None:
    baseline_signals = (
        Signal(1, Action.BUY),
        Signal(2, Action.BUY),
        Signal(3, Action.BUY),
        Signal(4, Action.HOLD),
    )
    candidate_signals = (
        Signal(1, Action.BUY),
        Signal(2, Action.HOLD),
        Signal(3, Action.HOLD),
        Signal(4, Action.HOLD),
    )
    baseline_result = _result(
        (
            *_round_trip(1, 11, entry=100.0, exit=110.0, fee=0.02, slip=0.004),
            *_round_trip(2, 12, entry=100.0, exit=90.0, fee=0.02, slip=0.004),
        )
    )
    attribution = btc_filter_attribution(baseline_signals, candidate_signals, baseline_result)
    assert attribution["baseline_buy_candidates"] == 3
    assert attribution["btc_confirmed_buys"] == 1
    assert attribution["btc_blocked_buys"] == 2
    assert attribution["blocked_baseline_trades"] == 1
    assert attribution["blocked_baseline_winners"] == 0
    assert attribution["blocked_baseline_losers"] == 1
    assert attribution["blocked_baseline_flats"] == 0
    assert attribution["blocked_baseline_net_pnl"] == pytest.approx(-2.048)
    assert attribution["blocked_baseline_avg_net_pnl"] == pytest.approx(-2.048)


def test_btc_filter_attribution_without_blocked_trades() -> None:
    signals = (Signal(1, Action.BUY), Signal(2, Action.HOLD))
    attribution = btc_filter_attribution(signals, signals, _result(()))
    assert attribution["btc_blocked_buys"] == 0
    assert attribution["blocked_baseline_trades"] == 0
    assert attribution["blocked_baseline_avg_net_pnl"] is None


def test_btc_filter_attribution_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError, match="length mismatch"):
        btc_filter_attribution((Signal(1, Action.BUY),), (), _result(()))


def test_btc_filter_attribution_rejects_non_buy_change() -> None:
    baseline = (Signal(1, Action.HOLD),)
    candidate = (Signal(1, Action.BUY),)
    with pytest.raises(ValueError, match="outside BUY"):
        btc_filter_attribution(baseline, candidate, _result(()))

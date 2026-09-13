"""Tests fase 17F: walk-forward MVP (geometría, métricas, agregado).

Sin holdout (solo bloqueo), sin auto-optimización. Las ventanas reales usan
rangos pequeños; la evidencia completa corre en el script de fase.
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from application.services.paper_engine import PaperEngine
from domain.risk.config import RiskConfig
from domain.trading.strategy import EmaRsiBaseline
from lab.experiment_spec import ExperimentSpec, spec_id
from lab.frozen_dataset import FrozenDatasetAdapter
from lab.session_runner import LabCandleEvent, LabSessionResult, LabSessionRunner
from lab.splits import FINAL_HOLDOUT_END, FINAL_HOLDOUT_START, WALK_FORWARD_END, WALK_FORWARD_START
from lab.walk_forward import (
    WindowResult,
    aggregate_results,
    make_window_result,
    trades_from_trace,
    walk_forward_windows,
    window_metrics,
)

REPO = Path(__file__).resolve().parents[2]
SPEC_ID = "ab" * 32
ENGINE_CONFIG = RiskConfig(stop_loss_required=False, version="risk-v1-nostop-mvp-a")


def _run_dev(row_start: int, row_end: int) -> LabSessionResult:
    adapter = FrozenDatasetAdapter.from_repo(
        REPO, symbol="ETHUSDT", timeframe="15m", row_start=row_start, row_end=row_end
    )
    return LabSessionRunner(
        adapter=adapter,
        strategy=EmaRsiBaseline(),
        engine=PaperEngine(config=ENGINE_CONFIG),
        experiment_spec_id=SPEC_ID,
    ).run()


def _event(
    ts: int, action: str, filled: bool, price: float | None = None, qty: float = 0.2
) -> LabCandleEvent:
    return LabCandleEvent(
        timestamp_ms=ts,
        action=action,
        filled=filled,
        exit_reason="",
        risk_reason="",
        exec_price=price,
        quantity=qty if filled else None,
        fee=0.02 if filled else 0.0,
        slippage_cost=0.004 if filled else 0.0,
        equity=1000.0,
    )


def _spec_with_fast(ema_fast: int) -> ExperimentSpec:
    return ExperimentSpec(
        dataset={
            "dataset_id": "BYBIT_ETHBTC_V001",
            "symbol": "ETHUSDT",
            "timeframe": "15m",
            "row_start": 62208,
            "row_end": 70848,
        },
        strategy={"name": "ema-rsi-baseline", "version": "baseline-v1", "ema_fast": ema_fast},
        risk={"version": "risk-v1-nostop-mvp-a"},
        execution={"model": "runtime-parity", "version": "mvp-a"},
        fees={"version": "bybit-spot-v1"},
        slippage={"version": "conservative-v1"},
        timing_model="mvp-a",
        holdout_protocol="deny-holdout",
        kernel_identity={"kernel_bundle_version": 1, "kernel_fingerprint": "00" * 32},
    )


def test_development_range_allowed() -> None:
    adapter = FrozenDatasetAdapter.from_repo(
        REPO, symbol="ETHUSDT", timeframe="15m", row_start=0, row_end=32
    )
    assert len(adapter) == 32


def test_walk_forward_range_denied_by_public_adapter() -> None:
    with pytest.raises(ValueError, match="WALK_FORWARD"):
        FrozenDatasetAdapter.from_repo(
            REPO, symbol="ETHUSDT", timeframe="15m", row_start=62208, row_end=62240
        )


def test_final_holdout_blocked() -> None:
    with pytest.raises(ValueError, match="FINAL_HOLDOUT"):
        FrozenDatasetAdapter.from_repo(
            REPO,
            symbol="ETHUSDT",
            timeframe="15m",
            row_start=FINAL_HOLDOUT_START,
            row_end=FINAL_HOLDOUT_END,
        )


def test_crossing_into_holdout_blocked() -> None:
    with pytest.raises(ValueError, match="FINAL_HOLDOUT"):
        FrozenDatasetAdapter.from_repo(
            REPO, symbol="ETHUSDT", timeframe="15m", row_start=88000, row_end=89000
        )


def test_windows_cover_walk_forward_without_overlap() -> None:
    windows = walk_forward_windows(3)
    assert [(w.row_start, w.row_end) for w in windows] == [
        (62208, 70848),
        (70848, 79488),
        (79488, 88128),
    ]
    assert windows[0].row_start == WALK_FORWARD_START
    assert windows[-1].row_end == WALK_FORWARD_END
    for prev, nxt in zip(windows, windows[1:], strict=False):
        assert nxt.row_start == prev.row_end


def test_windows_temporal_order_on_synthetic_authorized_data(
    synthetic_frozen_repo: Path,
) -> None:
    from lab.viability import AbsoluteViabilityEvidence, guarded_walk_forward_open

    last_ts = -1
    for window in walk_forward_windows(3):
        adapter = guarded_walk_forward_open(
            development_result="IMPROVED",
            absolute_viability=AbsoluteViabilityEvidence(
                net_pnl=1.0, expectancy=0.5, profit_factor=2.0
            ),
            human_authorized=True,
            repo_root=synthetic_frozen_repo,
            symbol="ETHUSDT",
            timeframe="15m",
            row_start=window.row_start,
            row_end=window.row_start + 16,
        )
        assert adapter is not None
        stamps = [candle.timestamp_ms for candle in adapter.candles]
        assert stamps == sorted(stamps)
        assert stamps[0] > last_ts
        last_ts = stamps[-1]


def test_windows_with_remainder_stay_contiguous() -> None:
    windows = walk_forward_windows(7)
    assert len(windows) == 7
    assert windows[0].row_start == WALK_FORWARD_START
    assert windows[-1].row_end == WALK_FORWARD_END
    sizes = {w.row_end - w.row_start for w in windows}
    assert max(sizes) - min(sizes) <= 1
    assert walk_forward_windows(1)[0].row_start == WALK_FORWARD_START


def test_invalid_window_counts_rejected() -> None:
    for bad in (0, -1, True, "3", 1.0, 25921):
        with pytest.raises(ValueError):
            walk_forward_windows(bad)  # type: ignore[arg-type]


def test_parameter_change_changes_spec_id() -> None:
    assert spec_id(_spec_with_fast(20)) != spec_id(_spec_with_fast(18))


def test_same_execution_reproduces_hashes() -> None:
    first = _run_dev(0, 48)
    second = _run_dev(0, 48)
    assert first.event_trace_hash == second.event_trace_hash
    assert first.metrics_hash_value == second.metrics_hash_value


def test_trades_from_trace_pairs_buy_sell() -> None:
    events = (
        _event(1, "HOLD", False),
        _event(2, "SELL", False),  # sin posición: se ignora
        _event(3, "BUY", True, price=100.0),
        _event(4, "HOLD", False),
        _event(5, "SELL", True, price=101.0),
        _event(6, "BUY", True, price=102.0),  # abierta al final: se ignora
    )
    trades = trades_from_trace(events)
    assert len(trades) == 1
    trade = trades[0]
    assert trade.entry_price == pytest.approx(100.0)
    assert trade.exit_price == pytest.approx(101.0)
    assert trade.gross_pnl == pytest.approx(0.2)
    assert trade.fees == pytest.approx(0.04)
    assert trade.net_pnl == pytest.approx(0.2 - 0.04 - 0.008)


def test_window_metrics_and_result_from_real_run() -> None:
    result = _run_dev(0, 48)
    metrics = window_metrics(result)
    assert metrics["trades"] >= 0
    assert metrics["return_pct"] == pytest.approx(metrics["net_pnl"] / 1000.0)
    window = walk_forward_windows(3)[0]
    item = make_window_result(window, result, run_id="wf-test-0")
    assert (item.row_start, item.row_end) == (window.row_start, window.row_end)
    assert item.first_timestamp_ms == result.events[0].timestamp_ms
    assert item.last_timestamp_ms == result.events[-1].timestamp_ms
    assert item.run_id == "wf-test-0"


def test_window_metrics_zero_initial_equity() -> None:
    result = LabSessionResult(
        experiment_spec_id=SPEC_ID,
        events=(),
        metrics=MappingProxyType({"equity_initial": 0.0}),
        event_trace_hash="aa" * 32,
        metrics_hash_value="bb" * 32,
    )
    metrics = window_metrics(result)
    assert metrics["trades"] == 0
    assert metrics["return_pct"] == 0.0
    assert metrics["profit_factor"] is None
    assert metrics["expectancy"] is None


def _window_result(
    index: int, net: float, ret: float, trades: int, dd: float = 0.01
) -> WindowResult:
    return WindowResult(
        index=index,
        row_start=index,
        row_end=index + 1,
        first_timestamp_ms=index,
        last_timestamp_ms=index,
        trades=trades,
        net_pnl=net,
        return_pct=ret,
        max_drawdown=dd,
        profit_factor=None,
        expectancy=None,
        experiment_spec_id=SPEC_ID,
        run_id=f"run-{index}",
        event_trace_hash="aa" * 32,
        metrics_hash="bb" * 32,
    )


def test_aggregate_results_hand_checked() -> None:
    agg = aggregate_results((_window_result(0, 10.0, 0.01, 2), _window_result(1, -4.0, -0.004, 1)))
    assert agg["total_windows"] == 2
    assert agg["profitable_windows"] == 1
    assert agg["losing_windows"] == 1
    assert agg["aggregate_net_pnl"] == pytest.approx(6.0)
    assert agg["aggregate_return_pct"] == pytest.approx(0.006)
    assert agg["median_window_return"] == pytest.approx(0.003)
    assert agg["worst_window_return"] == pytest.approx(-0.004)
    assert agg["total_trades"] == 3
    assert agg["profit_factor"] == pytest.approx(2.5)
    assert agg["expectancy"] == pytest.approx(2.0)


def test_aggregate_edge_cases() -> None:
    with pytest.raises(ValueError, match="no window results"):
        aggregate_results(())
    flat = aggregate_results((_window_result(0, 0.0, 0.0, 0),))
    assert flat["profit_factor"] is None
    assert flat["expectancy"] is None
    assert flat["profitable_windows"] == 0
    assert flat["losing_windows"] == 0
    only_wins = aggregate_results((_window_result(0, 5.0, 0.005, 1),))
    assert only_wins["profit_factor"] == float("inf")


def test_aggregate_is_deterministic() -> None:
    results = (_window_result(0, 10.0, 0.01, 2), _window_result(1, -4.0, -0.004, 1))
    assert aggregate_results(results) == aggregate_results(results)


def test_result_metrics_mapping() -> None:
    metrics: dict[str, Any] = dict(window_metrics(_run_dev(0, 48)))
    assert set(metrics) == {
        "trades",
        "net_pnl",
        "return_pct",
        "max_drawdown",
        "profit_factor",
        "expectancy",
    }

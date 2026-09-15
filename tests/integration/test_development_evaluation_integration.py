"""Phase 18B integration: real adapters + runner for both strategies on a DEV slice.

Covers the same economic conditions, identical DEVELOPMENT slices, aligned BTC
context, distinct SpecIds, deterministic metrics/comparison, blocked-buy
accounting, WALK_FORWARD not accessed and FINAL_HOLDOUT blocked/pristine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from application.services.paper_engine import PaperEngine
from domain.risk.config import RiskConfig
from domain.trading.strategy import EmaRsiBaseline
from lab.development_evaluation import (
    btc_filter_attribution,
    compare_metrics,
    count_signals,
    session_metrics,
)
from lab.experiment_spec import ExperimentSpec, spec_id
from lab.fingerprints import (
    ImportlibSourceResolver,
    StrategyDefinition,
    strategy_artifact_identity,
)
from lab.frozen_dataset import FrozenDatasetAdapter
from lab.session_runner import LabSessionResult, LabSessionRunner
from lab.splits import (
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    FINAL_HOLDOUT_END,
    FINAL_HOLDOUT_START,
    WALK_FORWARD_END,
    WALK_FORWARD_START,
    is_holdout_range,
)
from lab.strategies.ema_rsi_btc_context import EmaRsiBtcContext, strategy_definition

REPO = Path(__file__).resolve().parents[2]
ROW_START = DEVELOPMENT_START
ROW_END = 512
ENGINE_CONFIG = RiskConfig(stop_loss_required=False, version="risk-v1-nostop-mvp-a")
HOLDOUT_FILE = REPO / "holdout" / "v1.state.json"


def _dataset(*, with_context: bool) -> dict[str, object]:
    dataset: dict[str, object] = {
        "dataset_id": "BYBIT_ETHBTC_V001",
        "symbol": "ETHUSDT",
        "timeframe": "15m",
        "row_start": ROW_START,
        "row_end": ROW_END,
    }
    if with_context:
        dataset["context"] = {
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "row_start": ROW_START,
            "row_end": ROW_END,
        }
    return dataset


def _spec(*, name: str, version: str, identity: str, with_context: bool) -> ExperimentSpec:
    return ExperimentSpec(
        dataset=_dataset(with_context=with_context),
        strategy={"name": name, "version": version, "artifact_identity": identity},
        risk={"version": ENGINE_CONFIG.version, "capital": ENGINE_CONFIG.capital},
        execution={"model": "runtime-parity", "version": "mvp-a"},
        fees={"version": "bybit-spot-v1"},
        slippage={"version": "conservative-v1"},
        timing_model="mvp-a",
        holdout_protocol="deny-holdout",
        kernel_identity={"kernel_bundle_version": 1, "kernel_fingerprint": "00" * 32},
    )


def _adapter(symbol: str) -> FrozenDatasetAdapter:
    return FrozenDatasetAdapter.from_repo(
        REPO, symbol=symbol, timeframe="15m", row_start=ROW_START, row_end=ROW_END
    )


@pytest.mark.real_dataset
def test_both_strategies_share_economic_conditions_and_slices() -> None:
    primary = _adapter("ETHUSDT")
    context = _adapter("BTCUSDT")
    assert primary.range.row_start == context.range.row_start == ROW_START
    assert primary.range.row_end == context.range.row_end == ROW_END
    assert primary.range.dataset_id == context.range.dataset_id
    assert primary.range.manifest_sha == context.range.manifest_sha
    assert [c.timestamp_ms for c in primary.candles] == [c.timestamp_ms for c in context.candles]
    assert ROW_END <= DEVELOPMENT_END
    assert not is_holdout_range(ROW_START, ROW_END)

    resolver = ImportlibSourceResolver()
    baseline_defn = StrategyDefinition(
        strategy_id="ema-rsi-baseline",
        strategy_version="baseline-v1",
        kind="deterministic",
        normalized_config={"ema_fast": 20, "ema_slow": 50, "rsi_period": 14, "rsi_exit": 80.0},
        sources=("domain.trading.strategy",),
    )
    baseline_identity = strategy_artifact_identity(baseline_defn, resolver)
    candidate_identity = strategy_artifact_identity(strategy_definition(), resolver)
    assert baseline_identity != candidate_identity

    baseline_spec = _spec(
        name="ema-rsi-baseline",
        version="baseline-v1",
        identity=baseline_identity,
        with_context=False,
    )
    candidate_spec = _spec(
        name="EmaRsiBtcContext",
        version="ema-rsi-btc-context-v1",
        identity=candidate_identity,
        with_context=True,
    )
    assert spec_id(baseline_spec) != spec_id(candidate_spec)


@pytest.mark.real_dataset
def test_metrics_and_comparison_are_deterministic_and_blocked_accounting_holds() -> None:
    primary = _adapter("ETHUSDT")
    context = _adapter("BTCUSDT")
    linked = "18" * 32

    def run_candidate() -> LabSessionResult:
        return LabSessionRunner(
            adapter=primary,
            strategy=EmaRsiBtcContext.from_adapters(primary=primary, context=context),
            engine=PaperEngine(config=ENGINE_CONFIG),
            experiment_spec_id=linked,
        ).run()

    baseline_probe = EmaRsiBaseline()
    baseline_signals = tuple(baseline_probe.on_candle(candle) for candle in primary.candles)
    candidate_probe = EmaRsiBtcContext.from_adapters(primary=primary, context=context)
    candidate_signals = tuple(candidate_probe.on_candle(candle) for candle in primary.candles)

    baseline_result = LabSessionRunner(
        adapter=primary,
        strategy=EmaRsiBaseline(),
        engine=PaperEngine(config=ENGINE_CONFIG),
        experiment_spec_id=linked,
    ).run()
    first = run_candidate()
    second = run_candidate()
    assert first.event_trace_hash == second.event_trace_hash
    assert first.metrics_hash_value == second.metrics_hash_value

    baseline_metrics = {**count_signals(baseline_signals), **session_metrics(baseline_result)}
    candidate_metrics = {**count_signals(candidate_signals), **session_metrics(first)}
    assert candidate_metrics == {**count_signals(candidate_signals), **session_metrics(second)}

    first_cmp = compare_metrics(baseline_metrics, candidate_metrics)
    assert first_cmp == compare_metrics(baseline_metrics, candidate_metrics)

    attribution = btc_filter_attribution(baseline_signals, candidate_signals, baseline_result)
    assert (
        attribution["baseline_buy_candidates"]
        == attribution["btc_confirmed_buys"] + attribution["btc_blocked_buys"]
    )


def test_walk_forward_not_accessed_and_final_holdout_blocked() -> None:
    assert not (ROW_START < WALK_FORWARD_END and ROW_END > WALK_FORWARD_START)
    assert is_holdout_range(FINAL_HOLDOUT_START, FINAL_HOLDOUT_END)
    with pytest.raises(ValueError, match="FINAL_HOLDOUT"):
        FrozenDatasetAdapter.from_repo(
            REPO,
            symbol="ETHUSDT",
            timeframe="15m",
            row_start=FINAL_HOLDOUT_START,
            row_end=FINAL_HOLDOUT_END,
        )


@pytest.mark.real_dataset
def test_holdout_file_remains_pristine() -> None:
    import json

    before = HOLDOUT_FILE.read_bytes()
    _adapter("ETHUSDT")
    _adapter("BTCUSDT")
    assert HOLDOUT_FILE.read_bytes() == before
    assert json.loads(before.decode("utf-8"))["state"] == "PRISTINE"

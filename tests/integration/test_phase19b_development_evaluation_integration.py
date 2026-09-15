"""Phase 19B integration: baseline vs Donchian under identical economic conditions."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.services.paper_engine import PaperEngine
from domain.risk.config import RiskConfig
from domain.trading.strategy import EmaRsiBaseline
from lab.development_evaluation import compare_metrics, count_signals, session_metrics
from lab.experiment_spec import ExperimentSpec, spec_id
from lab.fingerprints import (
    ImportlibSourceResolver,
    StrategyDefinition,
    strategy_artifact_identity,
)
from lab.frozen_dataset import FrozenDatasetAdapter
from lab.session_runner import LabSessionResult, LabSessionRunner
from lab.splits import DEVELOPMENT_END, DEVELOPMENT_START, is_holdout_range
from lab.strategies.eth_donchian_breakout import (
    EthDonchianBreakout,
)
from lab.strategies.eth_donchian_breakout import (
    strategy_definition as donchian_definition,
)

REPO = Path(__file__).resolve().parents[2]
ROW_START = DEVELOPMENT_START
ROW_END = 512
ENGINE_CONFIG = RiskConfig(stop_loss_required=False, version="risk-v1-nostop-mvp-a")
HOLDOUT_FILE = REPO / "holdout" / "v1.state.json"

pytestmark = pytest.mark.real_dataset


def _spec(*, name: str, version: str, identity: str) -> ExperimentSpec:
    return ExperimentSpec(
        dataset={
            "dataset_id": "BYBIT_ETHBTC_V001",
            "symbol": "ETHUSDT",
            "timeframe": "15m",
            "row_start": ROW_START,
            "row_end": ROW_END,
        },
        strategy={"name": name, "version": version, "artifact_identity": identity},
        risk={"version": ENGINE_CONFIG.version, "capital": ENGINE_CONFIG.capital},
        execution={"model": "runtime-parity", "version": "mvp-a"},
        fees={"version": "bybit-spot-v1"},
        slippage={"version": "conservative-v1"},
        timing_model="mvp-a",
        holdout_protocol="deny-holdout",
        kernel_identity={"kernel_bundle_version": 1, "kernel_fingerprint": "00" * 32},
    )


def _adapter() -> FrozenDatasetAdapter:
    return FrozenDatasetAdapter.from_repo(
        REPO, symbol="ETHUSDT", timeframe="15m", row_start=ROW_START, row_end=ROW_END
    )


def test_identical_conditions_and_distinct_spec_ids() -> None:
    resolver = ImportlibSourceResolver()
    baseline_identity = strategy_artifact_identity(
        StrategyDefinition(
            strategy_id="ema-rsi-baseline",
            strategy_version="baseline-v1",
            kind="deterministic",
            normalized_config={
                "ema_fast": 20,
                "ema_slow": 50,
                "rsi_period": 14,
                "rsi_exit": 80.0,
            },
            sources=("domain.trading.strategy",),
        ),
        resolver,
    )
    donchian_identity = strategy_artifact_identity(donchian_definition(), resolver)
    assert baseline_identity != donchian_identity

    baseline_spec = _spec(
        name="ema-rsi-baseline", version="baseline-v1", identity=baseline_identity
    )
    donchian_spec = _spec(
        name="EthDonchianBreakout",
        version="eth-donchian-breakout-v1",
        identity=donchian_identity,
    )
    assert spec_id(baseline_spec) != spec_id(donchian_spec)

    primary = _adapter()
    assert ROW_END <= DEVELOPMENT_END
    assert not is_holdout_range(ROW_START, ROW_END)
    assert primary.range.row_start == ROW_START
    assert primary.range.row_end == ROW_END


def test_metrics_and_accounting_are_deterministic() -> None:
    primary = _adapter()
    linked = "19" * 32

    def run_baseline() -> LabSessionResult:
        return LabSessionRunner(
            adapter=primary,
            strategy=EmaRsiBaseline(),
            engine=PaperEngine(config=ENGINE_CONFIG),
            experiment_spec_id=linked,
        ).run()

    def run_donchian() -> LabSessionResult:
        return LabSessionRunner(
            adapter=primary,
            strategy=EthDonchianBreakout(candles=primary.candles),
            engine=PaperEngine(config=ENGINE_CONFIG),
            experiment_spec_id=linked,
        ).run()

    baseline_probe = EmaRsiBaseline()
    baseline_signals = tuple(baseline_probe.on_candle(candle) for candle in primary.candles)
    donchian_probe = EthDonchianBreakout(candles=primary.candles)
    donchian_signals = tuple(donchian_probe.on_candle(candle) for candle in primary.candles)

    baseline_first = run_baseline()
    baseline_second = run_baseline()
    donchian_first = run_donchian()
    donchian_second = run_donchian()

    for first, second in ((baseline_first, baseline_second), (donchian_first, donchian_second)):
        assert first.event_trace_hash == second.event_trace_hash
        assert first.metrics_hash_value == second.metrics_hash_value

    baseline_metrics = {**count_signals(baseline_signals), **session_metrics(baseline_first)}
    donchian_metrics = {**count_signals(donchian_signals), **session_metrics(donchian_first)}
    deltas = compare_metrics(baseline_metrics, donchian_metrics)
    assert deltas == compare_metrics(baseline_metrics, donchian_metrics)

    # Signal vs execution accounting separates signals from fills.
    buy_signals = sum(signal.action.value == "buy" for signal in donchian_signals)
    executed_buys = sum(event.filled and event.action == "BUY" for event in donchian_first.events)
    rejected_buys = sum(
        not event.filled and event.action == "BUY" for event in donchian_first.events
    )
    assert executed_buys + rejected_buys <= buy_signals


def test_holdout_file_remains_pristine() -> None:
    import json

    before = HOLDOUT_FILE.read_bytes()
    _adapter()
    assert HOLDOUT_FILE.read_bytes() == before
    assert json.loads(before.decode("utf-8"))["state"] == "PRISTINE"

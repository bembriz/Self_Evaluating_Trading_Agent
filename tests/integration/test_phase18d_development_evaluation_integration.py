"""Phase 18D integration: three strategies under identical economic conditions.

Covers same economic conditions, full DEVELOPMENT slice boundary, BTC alignment,
distinct SpecIds, deterministic metrics, deterministic comparison and the filter
accounting identity.
"""

from __future__ import annotations

from pathlib import Path

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
from lab.splits import DEVELOPMENT_END, DEVELOPMENT_START, is_holdout_range
from lab.strategies.ema_rsi_btc_context import (
    EmaRsiBtcContext,
)
from lab.strategies.ema_rsi_btc_context import (
    strategy_definition as context_definition,
)
from lab.strategies.ema_rsi_btc_regime import (
    EmaRsiBtcRegime,
)
from lab.strategies.ema_rsi_btc_regime import (
    strategy_definition as regime_definition,
)

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


def test_three_strategies_share_economic_conditions_and_slices() -> None:
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
    context_identity = strategy_artifact_identity(context_definition(), resolver)
    regime_identity = strategy_artifact_identity(regime_definition(), resolver)
    assert len({baseline_identity, context_identity, regime_identity}) == 3

    baseline_spec = _spec(
        name="ema-rsi-baseline",
        version="baseline-v1",
        identity=baseline_identity,
        with_context=False,
    )
    context_spec = _spec(
        name="EmaRsiBtcContext",
        version="ema-rsi-btc-context-v1",
        identity=context_identity,
        with_context=True,
    )
    regime_spec = _spec(
        name="EmaRsiBtcRegime",
        version="ema-rsi-btc-regime-v1",
        identity=regime_identity,
        with_context=True,
    )
    ids = {spec_id(baseline_spec), spec_id(context_spec), spec_id(regime_spec)}
    assert len(ids) == 3


def test_metrics_comparison_and_accounting_are_deterministic() -> None:
    primary = _adapter("ETHUSDT")
    context = _adapter("BTCUSDT")
    linked = "1d" * 32

    def run_baseline() -> LabSessionResult:
        return LabSessionRunner(
            adapter=primary,
            strategy=EmaRsiBaseline(),
            engine=PaperEngine(config=ENGINE_CONFIG),
            experiment_spec_id=linked,
        ).run()

    def run_context() -> LabSessionResult:
        return LabSessionRunner(
            adapter=primary,
            strategy=EmaRsiBtcContext.from_adapters(primary=primary, context=context),
            engine=PaperEngine(config=ENGINE_CONFIG),
            experiment_spec_id=linked,
        ).run()

    def run_regime() -> LabSessionResult:
        return LabSessionRunner(
            adapter=primary,
            strategy=EmaRsiBtcRegime.from_adapters(primary=primary, context=context),
            engine=PaperEngine(config=ENGINE_CONFIG),
            experiment_spec_id=linked,
        ).run()

    baseline_probe = EmaRsiBaseline()
    baseline_signals = tuple(baseline_probe.on_candle(candle) for candle in primary.candles)
    context_probe = EmaRsiBtcContext.from_adapters(primary=primary, context=context)
    context_signals = tuple(context_probe.on_candle(candle) for candle in primary.candles)
    regime_probe = EmaRsiBtcRegime.from_adapters(primary=primary, context=context)
    regime_signals = tuple(regime_probe.on_candle(candle) for candle in primary.candles)

    baseline_first = run_baseline()
    baseline_second = run_baseline()
    context_first = run_context()
    context_second = run_context()
    regime_first = run_regime()
    regime_second = run_regime()

    for first, second in (
        (baseline_first, baseline_second),
        (context_first, context_second),
        (regime_first, regime_second),
    ):
        assert first.event_trace_hash == second.event_trace_hash
        assert first.metrics_hash_value == second.metrics_hash_value

    baseline_metrics = {**count_signals(baseline_signals), **session_metrics(baseline_first)}
    context_metrics = {**count_signals(context_signals), **session_metrics(context_first)}
    regime_metrics = {**count_signals(regime_signals), **session_metrics(regime_first)}

    primary_deltas = compare_metrics(baseline_metrics, regime_metrics)
    secondary_deltas = compare_metrics(context_metrics, regime_metrics)
    assert primary_deltas == compare_metrics(baseline_metrics, regime_metrics)
    assert secondary_deltas == compare_metrics(context_metrics, regime_metrics)

    context_attr = btc_filter_attribution(baseline_signals, context_signals, baseline_first)
    regime_attr = btc_filter_attribution(baseline_signals, regime_signals, baseline_first)
    assert (
        context_attr["baseline_buy_candidates"]
        == context_attr["btc_confirmed_buys"] + context_attr["btc_blocked_buys"]
    )
    assert (
        regime_attr["baseline_buy_candidates"]
        == regime_attr["btc_confirmed_buys"] + regime_attr["btc_blocked_buys"]
    )
    assert context_attr["btc_confirmed_buys"] >= regime_attr["btc_confirmed_buys"]


def test_holdout_file_remains_pristine() -> None:
    import json

    before = HOLDOUT_FILE.read_bytes()
    _adapter("ETHUSDT")
    _adapter("BTCUSDT")
    assert HOLDOUT_FILE.read_bytes() == before
    assert json.loads(before.decode("utf-8"))["state"] == "PRISTINE"

"""Phase 18C DEVELOPMENT-only end-to-end regime candidate proof."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from application.services.paper_engine import PaperEngine
from domain.risk.config import RiskConfig
from domain.trading.signal import Action
from domain.trading.strategy import EmaRsiBaseline
from lab.experiment_spec import ExperimentSpec, spec_id
from lab.fingerprints import (
    ImportlibSourceResolver,
    StrategyDefinition,
    strategy_artifact_identity,
)
from lab.frozen_dataset import FrozenDatasetAdapter
from lab.session_runner import LabSessionRunner
from lab.splits import DEVELOPMENT_END, is_holdout_range
from lab.strategies.ema_rsi_btc_context import (
    strategy_definition as context_strategy_definition,
)
from lab.strategies.ema_rsi_btc_regime import (
    EmaRsiBtcRegime,
    strategy_definition,
)

REPO = Path(__file__).resolve().parents[2]
HOLDOUT_STATE = REPO / "holdout" / "v1.state.json"
ROW_START = 0
ROW_END = 5000


def _dataset_spec() -> dict[str, dict[str, object]]:
    return {
        "primary": {
            "dataset_id": "BYBIT_ETHBTC_V001",
            "symbol": "ETHUSDT",
            "timeframe": "15m",
            "row_start": ROW_START,
            "row_end": ROW_END,
        },
        "context": {
            "dataset_id": "BYBIT_ETHBTC_V001",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "row_start": ROW_START,
            "row_end": ROW_END,
        },
    }


def _spec(artifact_identity: str) -> ExperimentSpec:
    return ExperimentSpec(
        dataset=_dataset_spec(),
        strategy={
            "name": "EmaRsiBtcRegime",
            "version": "ema-rsi-btc-regime-v1",
            "artifact_identity": artifact_identity,
        },
        risk={"version": "risk-v1-nostop-mvp-a", "capital": 1000.0},
        execution={"model": "runtime-parity", "version": "mvp-a"},
        fees={"version": "bybit-spot-v1"},
        slippage={"version": "conservative-v1"},
        timing_model="mvp-a",
        holdout_protocol="deny-holdout",
        kernel_identity={"kernel_bundle_version": 1, "kernel_fingerprint": "00" * 32},
    )


def _strategy_decisions(
    primary: FrozenDatasetAdapter,
    context: FrozenDatasetAdapter,
) -> tuple[list[Any], list[Any]]:
    baseline = EmaRsiBaseline()
    candidate = EmaRsiBtcRegime.from_adapters(primary=primary, context=context)
    baseline_signals = [baseline.on_candle(candle) for candle in primary.candles]
    candidate_signals = [candidate.on_candle(candle) for candle in primary.candles]
    return baseline_signals, candidate_signals


@pytest.mark.e2e
def test_regime_full_development_chain_filters_buy_only_and_preserves_holdout() -> None:
    assert ROW_END <= DEVELOPMENT_END
    assert not is_holdout_range(ROW_START, ROW_END)
    holdout_before = HOLDOUT_STATE.read_bytes()
    requested_ranges: list[tuple[int, int]] = []

    def open_development(symbol: str) -> FrozenDatasetAdapter:
        requested_ranges.append((ROW_START, ROW_END))
        return FrozenDatasetAdapter.from_repo(
            REPO,
            symbol=symbol,
            timeframe="15m",
            row_start=ROW_START,
            row_end=ROW_END,
        )

    primary = open_development("ETHUSDT")
    context = open_development("BTCUSDT")
    assert tuple(c.timestamp_ms for c in primary.candles) == tuple(
        c.timestamp_ms for c in context.candles
    )

    resolver = ImportlibSourceResolver()
    artifact_identity = strategy_artifact_identity(strategy_definition(), resolver)
    linked_spec_id = spec_id(_spec(artifact_identity))
    baseline_signals, candidate_signals = _strategy_decisions(primary, context)
    blocked = sum(
        baseline.action is Action.BUY and candidate.action is Action.HOLD
        for baseline, candidate in zip(baseline_signals, candidate_signals, strict=True)
    )
    assert blocked > 0
    for baseline, candidate in zip(baseline_signals, candidate_signals, strict=True):
        if baseline.action is not Action.BUY:
            assert candidate == baseline

    result = LabSessionRunner(
        adapter=primary,
        strategy=EmaRsiBtcRegime.from_adapters(primary=primary, context=context),
        engine=PaperEngine(config=RiskConfig(stop_loss_required=False)),
        experiment_spec_id=linked_spec_id,
    ).run()
    assert result.experiment_spec_id == linked_spec_id
    assert len(result.events) == ROW_END - ROW_START
    assert sum(is_holdout_range(start, end) for start, end in requested_ranges) == 0
    assert HOLDOUT_STATE.read_bytes() == holdout_before


@pytest.mark.e2e
def test_regime_spec_id_differs_from_baseline_and_context() -> None:
    resolver = ImportlibSourceResolver()
    regime_identity = strategy_artifact_identity(strategy_definition(), resolver)
    context_identity = strategy_artifact_identity(context_strategy_definition(), resolver)
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
    assert regime_identity != baseline_identity
    assert regime_identity != context_identity
    assert spec_id(_spec(regime_identity)) != spec_id(_spec(context_identity))

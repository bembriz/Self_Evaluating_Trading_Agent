"""Phase 20A DEVELOPMENT-only end-to-end proof for the Bollinger strategy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from application.services.paper_engine import PaperEngine
from domain.risk.config import RiskConfig
from domain.trading.signal import Action
from lab.experiment_spec import ExperimentSpec, spec_id
from lab.fingerprints import (
    ImportlibSourceResolver,
    StrategyDefinition,
    strategy_artifact_identity,
)
from lab.frozen_dataset import FrozenDatasetAdapter
from lab.session_runner import LabSessionRunner
from lab.splits import DEVELOPMENT_END, is_holdout_range
from lab.strategies.ema_rsi_btc_context import strategy_definition as context_definition
from lab.strategies.ema_rsi_btc_regime import strategy_definition as regime_definition
from lab.strategies.eth_bollinger_mean_reversion import (
    EthBollingerMeanReversion,
    strategy_definition,
)
from lab.strategies.eth_donchian_breakout import strategy_definition as donchian_definition

REPO = Path(__file__).resolve().parents[2]
HOLDOUT_STATE = REPO / "holdout" / "v1.state.json"
ROW_START = 0
ROW_END = 5000


def _spec(artifact_identity: str) -> ExperimentSpec:
    return ExperimentSpec(
        dataset={
            "dataset_id": "BYBIT_ETHBTC_V001",
            "symbol": "ETHUSDT",
            "timeframe": "15m",
            "row_start": ROW_START,
            "row_end": ROW_END,
        },
        strategy={
            "name": "EthBollingerMeanReversion",
            "version": "eth-bollinger-mean-reversion-v1",
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


@pytest.mark.real_dataset
@pytest.mark.e2e
def test_bollinger_development_chain_and_holdout_pristine() -> None:
    assert ROW_END <= DEVELOPMENT_END
    assert not is_holdout_range(ROW_START, ROW_END)
    holdout_before = HOLDOUT_STATE.read_bytes()
    requested_ranges: list[tuple[int, int]] = []

    def open_development() -> FrozenDatasetAdapter:
        requested_ranges.append((ROW_START, ROW_END))
        return FrozenDatasetAdapter.from_repo(
            REPO, symbol="ETHUSDT", timeframe="15m", row_start=ROW_START, row_end=ROW_END
        )

    adapter = open_development()
    resolver = ImportlibSourceResolver()
    artifact_identity = strategy_artifact_identity(strategy_definition(), resolver)
    linked_spec_id = spec_id(_spec(artifact_identity))

    probe = EthBollingerMeanReversion.from_adapters(adapter=adapter)
    signals: list[Any] = [probe.on_candle(candle) for candle in adapter.candles]
    assert any(signal.action is Action.BUY for signal in signals)
    assert any(signal.action is Action.SELL for signal in signals)

    result = LabSessionRunner(
        adapter=adapter,
        strategy=EthBollingerMeanReversion.from_adapters(adapter=adapter),
        engine=PaperEngine(config=RiskConfig(stop_loss_required=False)),
        experiment_spec_id=linked_spec_id,
    ).run()
    assert result.experiment_spec_id == linked_spec_id
    assert len(result.events) == ROW_END - ROW_START
    assert sum(is_holdout_range(start, end) for start, end in requested_ranges) == 0
    assert HOLDOUT_STATE.read_bytes() == holdout_before


@pytest.mark.e2e
def test_bollinger_spec_id_differs_from_frozen_strategies() -> None:
    resolver = ImportlibSourceResolver()
    bollinger_identity = strategy_artifact_identity(strategy_definition(), resolver)
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
    regime_identity = strategy_artifact_identity(regime_definition(), resolver)
    identities = {
        bollinger_identity,
        baseline_identity,
        strategy_artifact_identity(context_definition(), resolver),
        regime_identity,
        strategy_artifact_identity(donchian_definition(), resolver),
    }
    assert len(identities) == 5
    assert spec_id(_spec(bollinger_identity)) != spec_id(_spec(regime_identity))

"""Phase 19A integration: real adapter + unchanged lab runner for the breakout."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from application.services.paper_engine import PaperEngine
from domain.risk.config import RiskConfig
from lab.frozen_dataset import FrozenDatasetAdapter
from lab.session_runner import LabSessionRunner
from lab.strategies.eth_donchian_breakout import EthDonchianBreakout

REPO = Path(__file__).resolve().parents[2]
SPEC_ID = "19" * 32
ROW_START = 0
ROW_END = 512


def _adapter() -> FrozenDatasetAdapter:
    return FrozenDatasetAdapter.from_repo(
        REPO, symbol="ETHUSDT", timeframe="15m", row_start=ROW_START, row_end=ROW_END
    )


@pytest.mark.integration
def test_real_adapter_runs_through_unchanged_lab_runner() -> None:
    adapter = _adapter()
    result = LabSessionRunner(
        adapter=adapter,
        strategy=EthDonchianBreakout.from_adapters(adapter=adapter),
        engine=PaperEngine(config=RiskConfig(stop_loss_required=False)),
        experiment_spec_id=SPEC_ID,
    ).run()
    assert [event.timestamp_ms for event in result.events] == [
        candle.timestamp_ms for candle in adapter.candles
    ]
    assert result.metrics["candles"] == ROW_END - ROW_START


@pytest.mark.integration
def test_real_adapter_candidate_is_reproducible() -> None:
    adapter = _adapter()

    def run() -> Any:
        return LabSessionRunner(
            adapter=adapter,
            strategy=EthDonchianBreakout.from_adapters(adapter=adapter),
            engine=PaperEngine(config=RiskConfig(stop_loss_required=False)),
            experiment_spec_id=SPEC_ID,
        ).run()

    first = run()
    second = run()
    assert second.event_trace() == first.event_trace()
    assert dict(second.metrics) == dict(first.metrics)
    assert second.event_trace_hash == first.event_trace_hash
    assert second.metrics_hash_value == first.metrics_hash_value

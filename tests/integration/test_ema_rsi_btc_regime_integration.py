"""Phase 18C integration with frozen adapters and unchanged lab runner."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from application.services.paper_engine import PaperEngine
from domain.risk.config import RiskConfig
from lab.frozen_dataset import FrozenDatasetAdapter
from lab.session_runner import LabSessionRunner
from lab.strategies.ema_rsi_btc_regime import EmaRsiBtcRegime

REPO = Path(__file__).resolve().parents[2]
SPEC_ID = "18" * 32
ROW_START = 0
ROW_END = 128

pytestmark = pytest.mark.real_dataset


def _adapter(symbol: str, timeframe: str, start: int, end: int) -> FrozenDatasetAdapter:
    return FrozenDatasetAdapter.from_repo(
        REPO,
        symbol=symbol,
        timeframe=timeframe,
        row_start=start,
        row_end=end,
    )


@pytest.fixture(scope="module")
def aligned_adapters() -> tuple[FrozenDatasetAdapter, FrozenDatasetAdapter]:
    return (
        _adapter("ETHUSDT", "15m", ROW_START, ROW_END),
        _adapter("BTCUSDT", "15m", ROW_START, ROW_END),
    )


def _with_range(
    adapter: FrozenDatasetAdapter,
    *,
    dataset_id: str | None = None,
    symbol: str | None = None,
    timeframe: str | None = None,
    manifest_sha: str | None = None,
) -> FrozenDatasetAdapter:
    changed = copy.copy(adapter)
    current = adapter.range
    changed._range = type(current)(
        dataset_id=current.dataset_id if dataset_id is None else dataset_id,
        symbol=current.symbol if symbol is None else symbol,
        timeframe=current.timeframe if timeframe is None else timeframe,
        row_start=current.row_start,
        row_end=current.row_end,
        manifest_sha=current.manifest_sha if manifest_sha is None else manifest_sha,
        csv_sha=current.csv_sha,
    )
    return changed


@pytest.mark.integration
def test_aligned_real_adapters_run_through_unchanged_lab_runner() -> None:
    primary = _adapter("ETHUSDT", "15m", ROW_START, ROW_END)
    context = _adapter("BTCUSDT", "15m", ROW_START, ROW_END)
    result = LabSessionRunner(
        adapter=primary,
        strategy=EmaRsiBtcRegime.from_adapters(primary=primary, context=context),
        engine=PaperEngine(config=RiskConfig(stop_loss_required=False)),
        experiment_spec_id=SPEC_ID,
    ).run()
    assert [event.timestamp_ms for event in result.events] == [
        candle.timestamp_ms for candle in primary.candles
    ]
    assert result.metrics["candles"] == ROW_END - ROW_START


@pytest.mark.integration
def test_real_adapter_candidate_is_reproducible() -> None:
    primary = _adapter("ETHUSDT", "15m", ROW_START, ROW_END)
    context = _adapter("BTCUSDT", "15m", ROW_START, ROW_END)

    def run() -> Any:
        return LabSessionRunner(
            adapter=primary,
            strategy=EmaRsiBtcRegime.from_adapters(primary=primary, context=context),
            engine=PaperEngine(config=RiskConfig(stop_loss_required=False)),
            experiment_spec_id=SPEC_ID,
        ).run()

    first = run()
    second = run()
    assert second.event_trace() == first.event_trace()
    assert dict(second.metrics) == dict(first.metrics)
    assert second.event_trace_hash == first.event_trace_hash
    assert second.metrics_hash_value == first.metrics_hash_value


@pytest.mark.integration
def test_adapter_range_mismatch_fails_closed() -> None:
    primary = _adapter("ETHUSDT", "15m", ROW_START, ROW_END)
    context = _adapter("BTCUSDT", "15m", ROW_START + 1, ROW_END + 1)
    with pytest.raises(ValueError, match="aligned"):
        EmaRsiBtcRegime.from_adapters(primary=primary, context=context)


@pytest.mark.integration
def test_adapter_symbol_and_timeframe_mismatch_fail_closed() -> None:
    primary = _adapter("BTCUSDT", "15m", ROW_START, ROW_END)
    context = _adapter("BTCUSDT", "1h", ROW_START, ROW_END)
    with pytest.raises(ValueError, match="aligned ETHUSDT"):
        EmaRsiBtcRegime.from_adapters(primary=primary, context=context)

    valid_primary = _adapter("ETHUSDT", "15m", ROW_START, ROW_END)
    with pytest.raises(ValueError, match="aligned BTCUSDT"):
        EmaRsiBtcRegime.from_adapters(primary=valid_primary, context=context)


@pytest.mark.integration
def test_primary_timeframe_identity_mismatch_fails_closed(
    aligned_adapters: tuple[FrozenDatasetAdapter, FrozenDatasetAdapter],
) -> None:
    primary, context = aligned_adapters
    with pytest.raises(ValueError, match="aligned ETHUSDT"):
        EmaRsiBtcRegime.from_adapters(primary=_with_range(primary, timeframe="1h"), context=context)


@pytest.mark.integration
def test_context_symbol_identity_mismatch_fails_closed(
    aligned_adapters: tuple[FrozenDatasetAdapter, FrozenDatasetAdapter],
) -> None:
    primary, context = aligned_adapters
    with pytest.raises(ValueError, match="aligned BTCUSDT"):
        EmaRsiBtcRegime.from_adapters(
            primary=primary, context=_with_range(context, symbol="ETHUSDT")
        )


@pytest.mark.integration
def test_context_dataset_identity_mismatch_fails_closed(
    aligned_adapters: tuple[FrozenDatasetAdapter, FrozenDatasetAdapter],
) -> None:
    primary, context = aligned_adapters
    with pytest.raises(ValueError, match="same dataset"):
        EmaRsiBtcRegime.from_adapters(
            primary=primary, context=_with_range(context, dataset_id="OTHER_DATASET")
        )


@pytest.mark.integration
def test_context_manifest_identity_mismatch_fails_closed(
    aligned_adapters: tuple[FrozenDatasetAdapter, FrozenDatasetAdapter],
) -> None:
    primary, context = aligned_adapters
    with pytest.raises(ValueError, match="same dataset"):
        EmaRsiBtcRegime.from_adapters(
            primary=primary, context=_with_range(context, manifest_sha="00" * 32)
        )

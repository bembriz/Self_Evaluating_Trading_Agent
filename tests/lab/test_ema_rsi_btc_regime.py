"""Phase 18C unit contract for the BTC trend+slope regime candidate."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

import pytest

from domain.market.candle import Candle
from domain.trading.signal import Action
from domain.trading.strategy import EmaRsiBaseline, EmaRsiConfig
from lab.experiment_spec import ExperimentSpec, spec_id
from lab.fingerprints import ImportlibSourceResolver, strategy_artifact_identity
from lab.splits import FINAL_HOLDOUT_END, FINAL_HOLDOUT_START, is_holdout_range
from lab.strategies.ema_rsi_btc_regime import (
    EmaRsiBtcRegime,
    EmaRsiBtcRegimeConfig,
    strategy_definition,
)

STEP_MS = 900_000
FAST_CONFIG = EmaRsiBtcRegimeConfig(
    ema_fast=2,
    ema_slow=3,
    rsi_period=2,
    rsi_exit=80.0,
    btc_ema_fast=2,
    btc_ema_slow=3,
    btc_slope_lookback=2,
)
SLOW_CONFIG = EmaRsiBtcRegimeConfig(
    ema_fast=2,
    ema_slow=3,
    rsi_period=2,
    rsi_exit=80.0,
    btc_ema_fast=2,
    btc_ema_slow=5,
    btc_slope_lookback=2,
)


def _candles(closes: Sequence[float], *, start_ms: int = 1_700_000_000_000) -> tuple[Candle, ...]:
    return tuple(
        Candle(
            timestamp_ms=start_ms + index * STEP_MS,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1.0,
            turnover=close,
        )
        for index, close in enumerate(closes)
    )


def _signals(
    eth_closes: Sequence[float],
    btc_closes: Sequence[float],
    config: EmaRsiBtcRegimeConfig = FAST_CONFIG,
) -> tuple[Any, ...]:
    eth = _candles(eth_closes)
    strategy = EmaRsiBtcRegime(
        primary_candles=eth,
        btc_candles=_candles(btc_closes),
        config=config,
    )
    return tuple(strategy.on_candle(candle) for candle in eth)


def test_eth_buy_with_bullish_slope_is_confirmed() -> None:
    signals = _signals([3, 2, 1, 2, 3], [1, 2, 3, 4, 5])
    assert signals[-1].action is Action.BUY
    assert signals[-1].reason == "ema_cross_up_btc_regime_confirmed"


def test_eth_buy_with_bearish_slope_is_blocked() -> None:
    signals = _signals([3, 2, 1, 2, 2, 2, 3], [1, 2, 3, 4, 5, 4, 3], SLOW_CONFIG)
    assert signals[-1].action is Action.HOLD
    assert signals[-1].reason == "btc_regime_block"


def test_eth_buy_with_bearish_trend_is_blocked() -> None:
    signals = _signals([3, 2, 1, 2, 3], [5, 4, 3, 2, 1])
    assert signals[-1].action is Action.HOLD
    assert signals[-1].reason == "btc_regime_block"


@pytest.mark.parametrize(
    "btc_closes",
    ([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]),
    ids=("bullish", "bearish"),
)
def test_eth_sell_is_preserved_for_ready_regime(btc_closes: list[float]) -> None:
    signals = _signals([1, 2, 3, 2, 1], btc_closes)
    assert signals[-1].action is Action.SELL
    assert signals[-1].reason == "ema_cross_down_or_rsi_exit"


def test_eth_sell_is_preserved_during_btc_warmup() -> None:
    config = replace(FAST_CONFIG, btc_ema_slow=6)
    signals = _signals([1, 2, 3, 2, 1], [1, 2, 3, 4, 5], config)
    assert signals[-1].action is Action.SELL
    assert signals[-1].reason == "ema_cross_down_or_rsi_exit"


def test_eth_hold_is_preserved_exactly() -> None:
    eth = _candles([1, 1, 1, 1, 1])
    baseline = EmaRsiBaseline(EmaRsiConfig(2, 3, 2, 80.0))
    expected = tuple(baseline.on_candle(candle) for candle in eth)
    strategy = EmaRsiBtcRegime(
        primary_candles=eth,
        btc_candles=_candles([5, 4, 3, 2, 1]),
        config=FAST_CONFIG,
    )
    actual = tuple(strategy.on_candle(candle) for candle in eth)
    assert actual == expected
    assert actual[-1].action is Action.HOLD


def test_eth_buy_is_blocked_during_btc_warmup() -> None:
    config = replace(FAST_CONFIG, btc_ema_slow=6)
    signals = _signals([3, 2, 1, 2, 3], [1, 2, 3, 4, 5], config)
    assert signals[-1].action is Action.HOLD
    assert signals[-1].reason == "btc_regime_block"


def test_eth_buy_is_blocked_during_slope_warmup() -> None:
    config = replace(FAST_CONFIG, btc_slope_lookback=4)
    signals = _signals([3, 2, 1, 2, 3], [1, 2, 3, 4, 5], config)
    assert signals[-1].action is Action.HOLD
    assert signals[-1].reason == "btc_regime_block"


def test_aligned_timestamps_are_accepted() -> None:
    eth = _candles([1, 2, 3])
    strategy = EmaRsiBtcRegime(primary_candles=eth, btc_candles=_candles([4, 5, 6]))
    assert [strategy.on_candle(candle).timestamp_ms for candle in eth] == [
        candle.timestamp_ms for candle in eth
    ]


def test_empty_or_different_length_sequences_fail_closed() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        EmaRsiBtcRegime(primary_candles=(), btc_candles=())
    with pytest.raises(ValueError, match="length"):
        EmaRsiBtcRegime(primary_candles=_candles([1, 2]), btc_candles=_candles([1]))


def test_misaligned_timestamp_fails_closed() -> None:
    eth = _candles([1, 2, 3])
    btc = list(_candles([4, 5, 6]))
    btc[1] = replace(btc[1], timestamp_ms=btc[1].timestamp_ms + 1)
    with pytest.raises(ValueError, match="timestamp"):
        EmaRsiBtcRegime(primary_candles=eth, btc_candles=btc)


def test_future_btc_changes_do_not_change_past_decisions() -> None:
    eth_closes = [3, 2, 1, 2, 2, 2, 3]
    original = _signals(eth_closes, [1, 2, 3, 4, 5, 6, 7], SLOW_CONFIG)
    corrupted = _signals(eth_closes, [1, 2, 3, 4, 5, 100_000, 1], SLOW_CONFIG)
    assert corrupted[:5] == original[:5]


def test_same_input_produces_same_decisions() -> None:
    first = _signals([3, 2, 1, 2, 3, 4], [5, 4, 3, 2, 1, 2])
    second = _signals([3, 2, 1, 2, 3, 4], [5, 4, 3, 2, 1, 2])
    assert second == first


def test_runner_sequence_must_match_preloaded_eth() -> None:
    eth = _candles([1, 2, 3])
    strategy = EmaRsiBtcRegime(primary_candles=eth, btc_candles=_candles([4, 5, 6]))
    strategy.on_candle(eth[0])
    with pytest.raises(ValueError, match="preloaded ETH"):
        strategy.on_candle(eth[2])


def test_runner_cannot_process_more_than_preloaded_eth() -> None:
    eth = _candles([1])
    strategy = EmaRsiBtcRegime(primary_candles=eth, btc_candles=_candles([2]))
    strategy.on_candle(eth[0])
    with pytest.raises(ValueError, match="exhausted"):
        strategy.on_candle(eth[0])


@pytest.mark.parametrize(
    "config",
    (
        replace(FAST_CONFIG, ema_fast=0),
        replace(FAST_CONFIG, rsi_period=-1),
        replace(FAST_CONFIG, btc_ema_slow=0),
        replace(FAST_CONFIG, btc_slope_lookback=0),
        replace(FAST_CONFIG, ema_fast=3, ema_slow=3),
        replace(FAST_CONFIG, btc_ema_fast=3, btc_ema_slow=3),
    ),
)
def test_invalid_period_config_fails_closed(config: EmaRsiBtcRegimeConfig) -> None:
    with pytest.raises(ValueError, match="period|fast|slope"):
        EmaRsiBtcRegime(
            primary_candles=_candles([1]),
            btc_candles=_candles([2]),
            config=config,
        )


def test_regime_config_changes_existing_strategy_artifact_identity() -> None:
    resolver = ImportlibSourceResolver()
    original = strategy_artifact_identity(strategy_definition(), resolver)
    changed_slope = strategy_artifact_identity(
        strategy_definition(replace(EmaRsiBtcRegimeConfig(), btc_slope_lookback=8)), resolver
    )
    changed_btc = strategy_artifact_identity(
        strategy_definition(replace(EmaRsiBtcRegimeConfig(), btc_ema_fast=21)), resolver
    )
    assert changed_slope != original
    assert changed_btc != original
    assert strategy_definition().sources == (
        "lab.strategies.ema_rsi_btc_regime",
        "domain.trading.strategy",
        "domain.market.indicators",
    )


def _spec_dataset(context_overrides: dict[str, object] | None = None) -> dict[str, object]:
    context: dict[str, object] = {
        "dataset_id": "BYBIT_ETHBTC_V001",
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "row_start": 0,
        "row_end": 5000,
    }
    context.update(context_overrides or {})
    return {
        "primary": {
            "dataset_id": "BYBIT_ETHBTC_V001",
            "symbol": "ETHUSDT",
            "timeframe": "15m",
            "row_start": 0,
            "row_end": 5000,
        },
        "context": context,
    }


def _spec(dataset: dict[str, object]) -> ExperimentSpec:
    return ExperimentSpec(
        dataset=dataset,
        strategy={"name": "EmaRsiBtcRegime", "version": "ema-rsi-btc-regime-v1"},
        risk={"version": "risk-v1"},
        execution={"model": "runtime-parity", "version": "mvp-a"},
        fees={"version": "bybit-spot-v1"},
        slippage={"version": "conservative-v1"},
        timing_model="mvp-a",
        holdout_protocol="deny-holdout",
        kernel_identity={"kernel_bundle_version": 1, "kernel_fingerprint": "00" * 32},
    )


@pytest.mark.parametrize(
    "context_overrides",
    (
        {"dataset_id": "OTHER"},
        {"row_start": 100},
        {"row_end": 4900},
    ),
)
def test_btc_dataset_or_slice_change_changes_spec_id(
    context_overrides: dict[str, object],
) -> None:
    assert spec_id(_spec(_spec_dataset(context_overrides))) != spec_id(_spec(_spec_dataset()))


def test_baseline_defaults_and_non_buy_semantics_remain_intact() -> None:
    assert EmaRsiConfig() == EmaRsiConfig(ema_fast=20, ema_slow=50, rsi_period=14, rsi_exit=80.0)
    assert EmaRsiBaseline.version == "baseline-v1"
    assert strategy_definition().normalized_config == {
        "ema_fast": 20,
        "ema_slow": 50,
        "rsi_period": 14,
        "rsi_exit": 80.0,
        "btc_ema_fast": 20,
        "btc_ema_slow": 50,
        "btc_slope_lookback": 4,
    }


def test_final_holdout_range_remains_blocked_without_reading_it() -> None:
    assert is_holdout_range(FINAL_HOLDOUT_START, FINAL_HOLDOUT_END)

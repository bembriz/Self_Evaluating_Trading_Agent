"""Phase 19A unit contract for the standalone Donchian breakout strategy."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

import pytest

from domain.market.candle import Candle
from domain.market.indicators import adx
from domain.trading.signal import Action
from lab.experiment_spec import ExperimentSpec, spec_id
from lab.fingerprints import ImportlibSourceResolver, strategy_artifact_identity
from lab.splits import FINAL_HOLDOUT_END, FINAL_HOLDOUT_START, is_holdout_range
from lab.strategies.eth_donchian_breakout import (
    EthDonchianBreakout,
    EthDonchianBreakoutConfig,
    strategy_definition,
)

STEP_MS = 900_000


def _candle(index: int, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        timestamp_ms=1_700_000_000_000 + index * STEP_MS,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1.0,
        turnover=close,
    )


def _rising(count: int) -> list[Candle]:
    return [_candle(i, 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i) for i in range(count)]


def _signals(
    candles: Sequence[Candle], config: EthDonchianBreakoutConfig | None = None
) -> list[Any]:
    strategy = EthDonchianBreakout(candles=candles, config=config)
    return [strategy.on_candle(candle) for candle in candles]


def test_breakout_above_prior_high_with_strong_adx_is_buy() -> None:
    signals = _signals(_rising(29))
    assert signals[-1].action is Action.BUY
    assert signals[-1].reason == "donchian_breakout_adx"


def test_close_equal_to_prior_high_is_not_buy() -> None:
    candles = _rising(29)
    prior_high = max(candle.high for candle in candles[8:28])
    candles[-1] = _candle(28, 100.0, prior_high + 1.0, 99.0, prior_high)
    signals = _signals(candles)
    assert signals[-1].action is Action.HOLD


def test_current_high_is_excluded_from_entry_window() -> None:
    candles = _rising(29)
    prior_high = max(candle.high for candle in candles[8:28])
    candles[-1] = _candle(28, 100.0, prior_high + 1000.0, 99.0, prior_high + 0.5)
    signals = _signals(candles)
    assert signals[-1].action is Action.BUY


def test_adx_equal_to_threshold_is_not_buy() -> None:
    candles = _rising(29)
    value = adx(candles, 14)[28]
    assert value is not None
    signals = _signals(candles, EthDonchianBreakoutConfig(adx_min=value))
    assert signals[-1].action is Action.HOLD


def test_adx_below_threshold_blocks_buy() -> None:
    candles = _rising(29)
    value = adx(candles, 14)[28]
    assert value is not None
    signals = _signals(candles, EthDonchianBreakoutConfig(adx_min=value + 1.0))
    assert signals[-1].action is Action.HOLD


def test_adx_unavailable_blocks_buy_but_not_entry_window() -> None:
    candles = _rising(27)
    prior_high = max(candle.high for candle in candles[6:26])
    candles[-1] = _candle(26, 100.0, prior_high + 1.0, 99.0, prior_high + 0.5)
    assert adx(candles, 14)[26] is None
    signals = _signals(candles)
    assert signals[-1].action is Action.HOLD


def test_close_below_prior_low_is_sell() -> None:
    candles = _rising(16)
    prior_low = min(candle.low for candle in candles[5:15])
    candles[-1] = _candle(15, prior_low - 1.0, prior_low, prior_low - 2.0, prior_low - 1.0)
    signals = _signals(candles)
    assert signals[-1].action is Action.SELL
    assert signals[-1].reason == "donchian_exit"


def test_close_equal_to_prior_low_is_not_sell() -> None:
    candles = _rising(16)
    prior_low = min(candle.low for candle in candles[5:15])
    candles[-1] = _candle(15, prior_low, prior_low + 1.0, prior_low - 1.0, prior_low)
    signals = _signals(candles)
    assert signals[-1].action is Action.HOLD


def test_current_low_is_excluded_from_exit_window() -> None:
    candles = _rising(16)
    prior_low = min(candle.low for candle in candles[5:15])
    candles[-1] = _candle(15, prior_low - 1.0, prior_low, 0.0, prior_low - 1.0)
    signals = _signals(candles)
    assert signals[-1].action is Action.SELL


def test_sell_is_independent_of_adx_availability() -> None:
    candles = _rising(16)
    prior_low = min(candle.low for candle in candles[5:15])
    candles[-1] = _candle(15, prior_low - 1.0, prior_low, prior_low - 2.0, prior_low - 1.0)
    assert adx(candles, 14)[15] is None
    signals = _signals(candles)
    assert signals[-1].action is Action.SELL


def test_sell_can_trigger_between_exit_and_entry_warmup() -> None:
    candles = _rising(15)
    prior_low = min(candle.low for candle in candles[4:14])
    candles[-1] = _candle(14, prior_low - 1.0, prior_low, prior_low - 2.0, prior_low - 1.0)
    signals = _signals(candles)
    assert 10 <= 14 < 20
    assert signals[-1].action is Action.SELL


def test_short_history_is_hold() -> None:
    candles = _rising(6)
    candles[-1] = _candle(5, 100.0, 101.0, 0.0, 1.0)
    signals = _signals(candles)
    assert signals[-1].action is Action.HOLD


def test_future_candles_do_not_change_past_signals() -> None:
    candles = _rising(30)
    original = _signals(candles)
    poisoned = list(candles)
    for index in range(26, 30):
        poisoned[index] = _candle(index, 1_000_000, 1_000_000, 1_000_000, 1_000_000)
    changed = _signals(poisoned)
    assert changed[:26] == original[:26]


def test_same_input_produces_same_signals() -> None:
    candles = _rising(30)
    assert _signals(candles) == _signals(candles)


def test_runner_sequence_must_match_preloaded_candles() -> None:
    candles = _rising(30)
    strategy = EthDonchianBreakout(candles=candles)
    strategy.on_candle(candles[0])
    with pytest.raises(ValueError, match="preloaded"):
        strategy.on_candle(candles[2])


def test_runner_cannot_process_more_than_preloaded_candles() -> None:
    candles = _rising(30)
    strategy = EthDonchianBreakout(candles=candles)
    for candle in candles:
        strategy.on_candle(candle)
    with pytest.raises(ValueError, match="exhausted"):
        strategy.on_candle(candles[-1])


@pytest.mark.parametrize(
    "config",
    (
        EthDonchianBreakoutConfig(entry_donchian_lookback=0),
        EthDonchianBreakoutConfig(exit_donchian_lookback=-1),
        EthDonchianBreakoutConfig(adx_period=0),
        EthDonchianBreakoutConfig(adx_min=-1.0),
    ),
)
def test_invalid_config_fails_closed(config: EthDonchianBreakoutConfig) -> None:
    with pytest.raises(ValueError, match="positive|non-negative"):
        EthDonchianBreakout(candles=_rising(30), config=config)


def test_empty_candles_fail_closed() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        EthDonchianBreakout(candles=[])


def test_identity_is_sensitive_to_every_parameter() -> None:
    resolver = ImportlibSourceResolver()
    original = strategy_artifact_identity(strategy_definition(), resolver)
    variants = (
        replace(EthDonchianBreakoutConfig(), entry_donchian_lookback=21),
        replace(EthDonchianBreakoutConfig(), exit_donchian_lookback=11),
        replace(EthDonchianBreakoutConfig(), adx_period=15),
        replace(EthDonchianBreakoutConfig(), adx_min=21.0),
    )
    for variant in variants:
        assert strategy_artifact_identity(strategy_definition(variant), resolver) != original
    assert strategy_definition().sources == (
        "lab.strategies.eth_donchian_breakout",
        "domain.market.indicators",
    )
    assert strategy_definition().normalized_config == {
        "entry_donchian_lookback": 20,
        "exit_donchian_lookback": 10,
        "adx_period": 14,
        "adx_min": 20.0,
    }


def _spec(row_end: int) -> ExperimentSpec:
    return ExperimentSpec(
        dataset={
            "dataset_id": "BYBIT_ETHBTC_V001",
            "symbol": "ETHUSDT",
            "timeframe": "15m",
            "row_start": 0,
            "row_end": row_end,
        },
        strategy={"name": "EthDonchianBreakout", "version": "eth-donchian-breakout-v1"},
        risk={"version": "risk-v1"},
        execution={"model": "runtime-parity", "version": "mvp-a"},
        fees={"version": "bybit-spot-v1"},
        slippage={"version": "conservative-v1"},
        timing_model="mvp-a",
        holdout_protocol="deny-holdout",
        kernel_identity={"kernel_bundle_version": 1, "kernel_fingerprint": "00" * 32},
    )


def test_dataset_slice_change_changes_spec_id() -> None:
    assert spec_id(_spec(5000)) != spec_id(_spec(4900))


def test_final_holdout_range_remains_blocked_without_reading_it() -> None:
    assert is_holdout_range(FINAL_HOLDOUT_START, FINAL_HOLDOUT_END)

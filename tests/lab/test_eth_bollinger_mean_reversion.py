"""Phase 20A unit contract for the ETH Bollinger mean-reversion strategy."""

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
from lab.strategies.eth_bollinger_mean_reversion import (
    EthBollingerMeanReversion,
    EthBollingerMeanReversionConfig,
    strategy_definition,
)

STEP_MS = 900_000
# Series that produces an excursion at index 30 (9.9) and a re-entry at 31 (9.97).
EXCURSION_REENTRY = [10.0] * 30 + [9.9, 9.97]
# Same shape but the re-entry close reaches the middle band.
MIDDLE_EXIT = [10.0] * 30 + [9.9, 10.0]
# Excursion/re-entry shape entirely inside ADX warmup (ADX first ready at 27).
ADX_WARMUP = [10.0] * 24 + [9.9, 9.97]


def _candle(index: int, close: float) -> Candle:
    return Candle(
        timestamp_ms=1_700_000_000_000 + index * STEP_MS,
        open=close,
        high=close + 0.05,
        low=close - 0.05,
        close=close,
        volume=1.0,
        turnover=close,
    )


def _candles(closes: Sequence[float]) -> list[Candle]:
    return [_candle(index, close) for index, close in enumerate(closes)]


def _signals(
    closes: Sequence[float], config: EthBollingerMeanReversionConfig | None = None
) -> list[Any]:
    candles = _candles(closes)
    strategy = EthBollingerMeanReversion(candles=candles, config=config)
    return [strategy.on_candle(candle) for candle in candles]


def test_excursion_reentry_and_low_adx_is_buy() -> None:
    signals = _signals(EXCURSION_REENTRY)
    assert signals[-1].action is Action.BUY
    assert signals[-1].reason == "bollinger_reentry_low_adx"


def test_previous_close_equal_to_lower_is_not_buy() -> None:
    # Multiplier chosen so close[30] == LOWER[30] exactly (strict excursion fails).
    config = replace(
        EthBollingerMeanReversionConfig(), bollinger_stddev_multiplier=4.358898943540718
    )
    signals = _signals(EXCURSION_REENTRY, config)
    assert signals[-1].action is not Action.BUY


def test_previous_close_above_lower_is_not_buy() -> None:
    config = replace(EthBollingerMeanReversionConfig(), bollinger_stddev_multiplier=5.0)
    signals = _signals(EXCURSION_REENTRY, config)
    assert signals[-1].action is not Action.BUY


def test_current_close_below_lower_is_not_buy() -> None:
    signals = _signals(EXCURSION_REENTRY)
    assert signals[30].action is not Action.BUY


def test_current_close_equal_to_lower_satisfies_reentry() -> None:
    # Multiplier chosen so close[31] == LOWER[31] exactly (inclusive re-entry).
    config = replace(
        EthBollingerMeanReversionConfig(), bollinger_stddev_multiplier=1.0480736989205526
    )
    signals = _signals(EXCURSION_REENTRY, config)
    assert signals[-1].action is Action.BUY


def test_adx_below_threshold_permits_buy() -> None:
    value = adx(_candles(EXCURSION_REENTRY), 14)[31]
    assert value is not None and value < 20.0
    signals = _signals(EXCURSION_REENTRY)
    assert signals[-1].action is Action.BUY


def test_adx_equal_to_threshold_blocks_buy() -> None:
    value = adx(_candles(EXCURSION_REENTRY), 14)[31]
    assert value is not None
    config = replace(EthBollingerMeanReversionConfig(), adx_max=value)
    signals = _signals(EXCURSION_REENTRY, config)
    assert signals[-1].action is Action.HOLD


def test_adx_above_threshold_blocks_buy() -> None:
    config = replace(EthBollingerMeanReversionConfig(), adx_max=5.0)
    signals = _signals(EXCURSION_REENTRY, config)
    assert signals[-1].action is Action.HOLD


def test_adx_unavailable_blocks_buy() -> None:
    signals = _signals(ADX_WARMUP)
    assert adx(_candles(ADX_WARMUP), 14)[25] is None
    assert signals[-1].action is Action.HOLD


def test_close_at_or_above_middle_is_sell() -> None:
    signals = _signals(MIDDLE_EXIT)
    assert signals[-1].action is Action.SELL
    assert signals[-1].reason == "bollinger_middle_exit"


def test_close_equal_to_middle_is_sell() -> None:
    signals = _signals([10.0] * 20)
    assert signals[19].action is Action.SELL


def test_sell_is_independent_of_adx() -> None:
    value = adx(_candles(MIDDLE_EXIT), 14)[31]
    assert value is not None
    for adx_max in (0.0, value, 100.0):
        config = replace(EthBollingerMeanReversionConfig(), adx_max=adx_max)
        assert _signals(MIDDLE_EXIT, config)[-1].action is Action.SELL


def test_sell_works_during_bollinger_warmup_without_adx() -> None:
    signals = _signals([10.0] * 20)
    assert adx(_candles([10.0] * 20), 14)[19] is None
    assert signals[19].action is Action.SELL


def test_sell_precedence_over_buy() -> None:
    signals = _signals(MIDDLE_EXIT)
    # At index 31 both re-entry BUY and close >= middle hold; SELL must win.
    assert signals[-1].action is Action.SELL


def test_bollinger_warmup_is_hold() -> None:
    signals = _signals([10.0] * 20)
    assert all(signal.action is Action.HOLD for signal in signals[:19])


def test_buy_cannot_occur_before_inputs_ready() -> None:
    signals = _signals(ADX_WARMUP)
    assert all(signal.action is not Action.BUY for signal in signals)


def test_future_candles_do_not_change_past_signals() -> None:
    closes = [10.0] * 30 + [9.9, 9.97] + [10.0] * 5
    original = _signals(closes)
    poisoned = list(closes)
    for index in range(32, 37):
        poisoned[index] = 1_000_000.0
    changed = _signals(poisoned)
    assert changed[:32] == original[:32]


def test_same_input_produces_same_signals() -> None:
    assert _signals(EXCURSION_REENTRY) == _signals(EXCURSION_REENTRY)


def test_runner_sequence_must_match_preloaded_candles() -> None:
    candles = _candles(EXCURSION_REENTRY)
    strategy = EthBollingerMeanReversion(candles=candles)
    strategy.on_candle(candles[0])
    with pytest.raises(ValueError, match="preloaded"):
        strategy.on_candle(candles[2])


def test_runner_cannot_process_more_than_preloaded_candles() -> None:
    candles = _candles([10.0] * 20)
    strategy = EthBollingerMeanReversion(candles=candles)
    for candle in candles:
        strategy.on_candle(candle)
    with pytest.raises(ValueError, match="exhausted"):
        strategy.on_candle(candles[-1])


@pytest.mark.parametrize(
    "config",
    (
        EthBollingerMeanReversionConfig(bollinger_period=0),
        EthBollingerMeanReversionConfig(bollinger_stddev_multiplier=0.0),
        EthBollingerMeanReversionConfig(adx_period=0),
        EthBollingerMeanReversionConfig(adx_max=-1.0),
    ),
)
def test_invalid_config_fails_closed(config: EthBollingerMeanReversionConfig) -> None:
    with pytest.raises(ValueError, match="period|multiplier|adx"):
        EthBollingerMeanReversion(candles=_candles([10.0] * 20), config=config)


def test_empty_candles_fail_closed() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        EthBollingerMeanReversion(candles=[])


def test_identity_is_sensitive_to_every_parameter() -> None:
    resolver = ImportlibSourceResolver()
    original = strategy_artifact_identity(strategy_definition(), resolver)
    variants = (
        replace(EthBollingerMeanReversionConfig(), bollinger_period=21),
        replace(EthBollingerMeanReversionConfig(), bollinger_stddev_multiplier=2.5),
        replace(EthBollingerMeanReversionConfig(), adx_period=15),
        replace(EthBollingerMeanReversionConfig(), adx_max=21.0),
    )
    for variant in variants:
        assert strategy_artifact_identity(strategy_definition(variant), resolver) != original
    assert strategy_definition().sources == (
        "lab.strategies.eth_bollinger_mean_reversion",
        "domain.market.indicators",
    )
    assert strategy_definition().normalized_config == {
        "bollinger_period": 20,
        "bollinger_stddev_multiplier": 2.0,
        "adx_period": 14,
        "adx_max": 20.0,
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
        strategy={
            "name": "EthBollingerMeanReversion",
            "version": "eth-bollinger-mean-reversion-v1",
        },
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

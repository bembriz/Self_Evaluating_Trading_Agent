#!/usr/bin/env python3
"""Functional DEVELOPMENT smoke for EmaRsiBtcRegime-v1."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from domain.market.candle import Candle
from domain.trading.signal import Action
from domain.trading.strategy import EmaRsiBaseline, EmaRsiConfig
from lab.frozen_dataset import FrozenDatasetAdapter
from lab.splits import DEVELOPMENT_END, is_holdout_range
from lab.strategies.ema_rsi_btc_regime import EmaRsiBtcRegime, EmaRsiBtcRegimeConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
ROW_START = 0
ROW_END = 5000


def decision_counts(
    primary_candles: Sequence[Candle],
    btc_candles: Sequence[Candle],
    *,
    config: EmaRsiBtcRegimeConfig | None = None,
) -> dict[str, int]:
    """Count strategy decisions only; fills and orders are intentionally absent."""
    candidate_config = config or EmaRsiBtcRegimeConfig()
    baseline = EmaRsiBaseline(
        EmaRsiConfig(
            ema_fast=candidate_config.ema_fast,
            ema_slow=candidate_config.ema_slow,
            rsi_period=candidate_config.rsi_period,
            rsi_exit=candidate_config.rsi_exit,
        )
    )
    candidate = EmaRsiBtcRegime(
        primary_candles=primary_candles,
        btc_candles=btc_candles,
        config=candidate_config,
    )
    baseline_signals = tuple(baseline.on_candle(candle) for candle in primary_candles)
    candidate_signals = tuple(candidate.on_candle(candle) for candle in primary_candles)
    baseline_buys = sum(signal.action is Action.BUY for signal in baseline_signals)
    candidate_buys = sum(signal.action is Action.BUY for signal in candidate_signals)
    blocked_buys = sum(
        baseline_signal.action is Action.BUY and candidate_signal.action is Action.HOLD
        for baseline_signal, candidate_signal in zip(
            baseline_signals, candidate_signals, strict=True
        )
    )
    if candidate_buys + blocked_buys != baseline_buys:
        raise RuntimeError("BTC regime changed decisions outside the BUY filter")
    return {
        "BASELINE_BUY_SIGNALS": baseline_buys,
        "BTC_REGIME_BUY_SIGNALS": candidate_buys,
        "BTC_BLOCKED_BUYS": blocked_buys,
    }


def development_smoke(repo_root: Path = REPO_ROOT) -> dict[str, object]:
    """Run the fixed functional smoke on aligned official DEVELOPMENT data."""
    if ROW_END > DEVELOPMENT_END or is_holdout_range(ROW_START, ROW_END):
        raise RuntimeError("smoke range must remain inside DEVELOPMENT")
    requested_ranges: list[tuple[str, int, int]] = []

    def open_development(symbol: str) -> FrozenDatasetAdapter:
        requested_ranges.append((symbol, ROW_START, ROW_END))
        return FrozenDatasetAdapter.from_repo(
            repo_root,
            symbol=symbol,
            timeframe="15m",
            row_start=ROW_START,
            row_end=ROW_END,
        )

    primary = open_development("ETHUSDT")
    context = open_development("BTCUSDT")
    counts = decision_counts(primary.candles, context.candles)
    if counts["BTC_BLOCKED_BUYS"] <= 0:
        raise RuntimeError("fixed smoke range contains no BTC-regime-blocked BUY candidates")
    holdout_reads = sum(is_holdout_range(start, end) for _, start, end in requested_ranges)
    return {
        "STRATEGY": "EmaRsiBtcRegime-v1",
        "DATASET_ID": primary.range.dataset_id,
        "PRIMARY_SYMBOL": primary.range.symbol,
        "CONTEXT_SYMBOL": context.range.symbol,
        "TIMEFRAME": primary.range.timeframe,
        "ROW_START": ROW_START,
        "ROW_END": ROW_END,
        "REQUESTED_RANGES": [
            {"symbol": symbol, "row_start": start, "row_end": end}
            for symbol, start, end in requested_ranges
        ],
        "TIMESTAMP_ALIGNMENT": "PASS",
        "COUNTER_UNIT": "strategy_decisions",
        **counts,
        "EDGE_PRESENT": "NOT_EVALUATED",
        "STRATEGY_PROMOTABLE": "NOT_EVALUATED",
        "FINAL_HOLDOUT_READS": holdout_reads,
        "FINAL_HOLDOUT_EXECUTIONS": 0,
    }


def main() -> int:
    print(json.dumps(development_smoke(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

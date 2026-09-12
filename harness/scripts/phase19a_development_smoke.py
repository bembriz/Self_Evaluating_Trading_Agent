#!/usr/bin/env python3
"""Functional DEVELOPMENT smoke for EthDonchianBreakout-v1 (no PnL)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from domain.market.candle import Candle
from domain.market.indicators import adx
from domain.trading.signal import Action
from lab.frozen_dataset import FrozenDatasetAdapter
from lab.splits import DEVELOPMENT_END, is_holdout_range
from lab.strategies.eth_donchian_breakout import EthDonchianBreakout

REPO_ROOT = Path(__file__).resolve().parents[2]
ROW_START = 0
ROW_END = 5000


def decision_counts(candles: Sequence[Candle]) -> dict[str, int]:
    """Count strategy decisions only; no fills, orders, or PnL."""
    strategy = EthDonchianBreakout(candles=candles)
    buys = sells = holds = 0
    for candle in candles:
        signal = strategy.on_candle(candle)
        if signal.action is Action.BUY:
            buys += 1
        elif signal.action is Action.SELL:
            sells += 1
        else:
            holds += 1
    return {"SIGNALS_BUY": buys, "SIGNALS_SELL": sells, "SIGNALS_HOLD": holds}


def first_adx_index(candles: Sequence[Candle], period: int = 14) -> int | None:
    for index, value in enumerate(adx(candles, period)):
        if value is not None:
            return index
    return None


def development_smoke(repo_root: Path = REPO_ROOT) -> dict[str, object]:
    """Run the fixed functional smoke on official DEVELOPMENT data."""
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
    counts = decision_counts(primary.candles)
    if counts["SIGNALS_BUY"] <= 0 or counts["SIGNALS_SELL"] <= 0 or counts["SIGNALS_HOLD"] <= 0:
        raise RuntimeError("fixed smoke range does not exercise all decision paths")
    ready_index = first_adx_index(primary.candles)
    if ready_index != 27:
        raise RuntimeError(f"ADX first index mismatch: {ready_index}")
    holdout_reads = sum(is_holdout_range(start, end) for _, start, end in requested_ranges)
    return {
        "STRATEGY": "EthDonchianBreakout-v1",
        "DATASET_ID": primary.range.dataset_id,
        "PRIMARY_SYMBOL": primary.range.symbol,
        "TIMEFRAME": primary.range.timeframe,
        "ROW_START": ROW_START,
        "ROW_END": ROW_END,
        "REQUESTED_RANGES": [
            {"symbol": symbol, "row_start": start, "row_end": end}
            for symbol, start, end in requested_ranges
        ],
        "COUNTER_UNIT": "strategy_decisions",
        **counts,
        "FIRST_ADX_INDEX": ready_index,
        "ADX_PERIOD": 14,
        "ENTRY_DONCHIAN_LOOKBACK": 20,
        "EXIT_DONCHIAN_LOOKBACK": 10,
        "ADX_MIN": 20,
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

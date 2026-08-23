"""Features agregadas del order book (PRD §14: persistir features, no deltas)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OrderBookFeatureSnapshot:
    symbol: str
    window_start_ms: int
    window_end_ms: int
    best_bid: float | None
    best_ask: float | None
    spread: float | None
    spread_pct: float | None
    bid_depth: float
    ask_depth: float
    imbalance: float | None

"""Eventos del stream de market data en tiempo real (PRD §13–14)."""

from __future__ import annotations

from dataclasses import dataclass

from domain.market.candle import Candle, Timeframe
from domain.market.orderbook import OrderBookLevel


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    symbol: str
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    update_id: int
    seq: int


@dataclass(frozen=True, slots=True)
class OrderBookDelta:
    symbol: str
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    update_id: int
    seq: int


@dataclass(frozen=True, slots=True)
class KlineUpdate:
    symbol: str
    interval: Timeframe
    start_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float
    confirm: bool

    def to_candle(self) -> Candle | None:
        """Solo una vela confirmada puede usarse (PRD §13.2)."""
        if not self.confirm:
            return None
        return Candle(
            timestamp_ms=self.start_ms,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            turnover=self.turnover,
        )

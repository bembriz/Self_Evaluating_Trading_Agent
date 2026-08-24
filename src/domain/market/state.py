"""Estado de mercado estructurado (PRD §15–16): features multi-timeframe + régimen.

Todas las entidades son inmutables (frozen) y puras, sin I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.market.candle import Timeframe
from domain.market.features import OrderBookFeatureSnapshot
from domain.market.orderbook import MarketDataHealth
from domain.market.regime import MarketRegime


@dataclass(frozen=True, slots=True)
class TimeframeFeatures:
    timeframe: Timeframe
    close: float | None
    ema_fast: float | None
    ema_slow: float | None
    rsi: float | None
    atr: float | None
    vwap: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None
    momentum: float | None
    realized_volatility: float | None
    relative_volume: float | None


@dataclass(frozen=True, slots=True)
class BtcContext:
    symbol: str
    close: float | None
    momentum: float | None
    rsi: float | None


@dataclass(frozen=True, slots=True)
class MarketState:
    symbol: str
    timestamp_ms: int
    health: MarketDataHealth
    regime: MarketRegime | None
    timeframes: dict[Timeframe, TimeframeFeatures]
    orderbook: OrderBookFeatureSnapshot | None
    btc: BtcContext | None

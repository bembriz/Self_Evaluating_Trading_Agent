"""Feature Engine puro (PRD §15): ensambla MarketState desde candles + order book + BTC.

Transformación pura y causal: sin I/O ni estado mutable. El valor en el instante ``t``
solo usa velas confirmadas con ``timestamp_ms <= t``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from domain.market.candle import Candle, Timeframe
from domain.market.features import OrderBookFeatureSnapshot
from domain.market.indicators import (
    atr,
    ema,
    macd,
    momentum,
    realized_volatility,
    relative_volume,
    rsi,
    vwap,
)
from domain.market.orderbook import MarketDataHealth
from domain.market.regime import MarketRegime, RegimeClassifier
from domain.market.state import BtcContext, MarketState, TimeframeFeatures

BTC_SYMBOL = "BTCUSDT"


@dataclass(frozen=True, slots=True)
class FeatureEngineConfig:
    rsi_period: int = 14
    ema_fast: int = 20
    ema_slow: int = 50
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 14
    momentum_period: int = 20
    realized_vol_window: int = 20
    relative_volume_window: int = 20
    regime_timeframe: Timeframe = Timeframe.H1


class FeatureEngine:
    def __init__(
        self,
        config: FeatureEngineConfig | None = None,
        regime: RegimeClassifier | None = None,
    ) -> None:
        self._config = config or FeatureEngineConfig()
        self._regime = regime or RegimeClassifier()

    def compute_state(
        self,
        symbol: str,
        health: MarketDataHealth,
        candles_by_timeframe: Mapping[Timeframe, Sequence[Candle]],
        orderbook: OrderBookFeatureSnapshot | None = None,
        btc_candles: Sequence[Candle] | None = None,
    ) -> MarketState:
        cfg = self._config
        timeframes = {
            tf: self._timeframe_features(tf, candles, cfg)
            for tf, candles in candles_by_timeframe.items()
        }
        timestamp_ms = max(
            (candles[-1].timestamp_ms for candles in candles_by_timeframe.values() if candles),
            default=0,
        )
        regime = self._classify_regime(candles_by_timeframe)
        btc = self._btc_context(btc_candles, cfg)
        return MarketState(
            symbol=symbol,
            timestamp_ms=timestamp_ms,
            health=health,
            regime=regime,
            timeframes=timeframes,
            orderbook=orderbook,
            btc=btc,
        )

    def _timeframe_features(
        self, tf: Timeframe, candles: Sequence[Candle], cfg: FeatureEngineConfig
    ) -> TimeframeFeatures:
        closes = [c.close for c in candles]
        ema_fast = ema(closes, cfg.ema_fast)
        ema_slow = ema(closes, cfg.ema_slow)
        m = macd(closes, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)
        rsi_series = rsi(closes, cfg.rsi_period)
        atr_series = atr(candles, cfg.atr_period)
        vwap_series = vwap(candles)
        momentum_series = momentum(closes, cfg.momentum_period)
        vol_series = realized_volatility(closes, cfg.realized_vol_window)
        rel_vol_series = relative_volume(candles, cfg.relative_volume_window)
        return TimeframeFeatures(
            timeframe=tf,
            close=closes[-1] if closes else None,
            ema_fast=ema_fast[-1] if ema_fast else None,
            ema_slow=ema_slow[-1] if ema_slow else None,
            rsi=rsi_series[-1] if rsi_series else None,
            atr=atr_series[-1] if atr_series else None,
            vwap=vwap_series[-1] if vwap_series else None,
            macd=m.macd[-1] if m.macd else None,
            macd_signal=m.signal[-1] if m.signal else None,
            macd_histogram=m.histogram[-1] if m.histogram else None,
            momentum=momentum_series[-1] if momentum_series else None,
            realized_volatility=vol_series[-1] if vol_series else None,
            relative_volume=rel_vol_series[-1] if rel_vol_series else None,
        )

    def _classify_regime(
        self, candles_by_timeframe: Mapping[Timeframe, Sequence[Candle]]
    ) -> MarketRegime | None:
        cfg = self._config
        preferred = candles_by_timeframe.get(cfg.regime_timeframe)
        if preferred:
            return self._regime.classify(preferred)
        if candles_by_timeframe:
            longest = max(candles_by_timeframe.values(), key=len, default=())
            return self._regime.classify(longest)
        return None

    @staticmethod
    def _btc_context(
        btc_candles: Sequence[Candle] | None, cfg: FeatureEngineConfig
    ) -> BtcContext | None:
        if not btc_candles:
            return None
        closes = [c.close for c in btc_candles]
        rsi_series = rsi(closes, cfg.rsi_period)
        momentum_series = momentum(closes, cfg.momentum_period)
        return BtcContext(
            symbol=BTC_SYMBOL,
            close=closes[-1],
            momentum=momentum_series[-1],
            rsi=rsi_series[-1],
        )

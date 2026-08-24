"""Tests anti-lookahead (PRD §34): una feature en t no puede depender de datos > t.

Patrón: (1) envenenar el futuro del dataset y verificar que la salida en el pasado no
cambia; (2) replay truncado — computar hasta t da el mismo estado que computar hasta
t+k y mirar t.
"""

from __future__ import annotations

from domain.market.candle import Candle, Timeframe
from domain.market.feature_engine import FeatureEngine
from domain.market.indicators import atr, ema, macd, rsi
from domain.market.orderbook import MarketDataHealth
from domain.market.regime import RegimeClassifier


def _series(n: int, start: float = 100.0, step: float = 0.002) -> list[Candle]:
    out: list[Candle] = []
    prev = start
    for i in range(n):
        close = prev * (1 + step)
        out.append(Candle(i * 3600_000, prev, close + 5, prev - 5, close, 1.0, close))
        prev = close
    return out


def _poisoned_candle(i: int) -> Candle:
    return Candle(i * 3600_000, 10**9, 10**9, 10**9, 10**9, 0.0, 0.0)


def test_ema_no_lookahead() -> None:
    candles = _series(150)
    closes = [c.close for c in candles]
    base = ema(closes, 20)
    poisoned = closes[:100] + [10**9] * (len(closes) - 100)
    assert ema(poisoned, 20)[:100] == base[:100]


def test_rsi_no_lookahead() -> None:
    candles = _series(150)
    closes = [c.close for c in candles]
    base = rsi(closes, 14)
    poisoned = closes[:100] + [1e-9] * (len(closes) - 100)
    assert rsi(poisoned, 14)[:100] == base[:100]


def test_atr_no_lookahead() -> None:
    candles = _series(150)
    base = atr(candles, 14)
    poisoned = candles[:100] + [_poisoned_candle(i) for i in range(100, 150)]
    assert atr(poisoned, 14)[:100] == base[:100]


def test_macd_no_lookahead() -> None:
    candles = _series(150)
    closes = [c.close for c in candles]
    base = macd(closes).macd
    poisoned = closes[:100] + [10**9] * (len(closes) - 100)
    assert macd(poisoned).macd[:100] == base[:100]


def test_regime_no_lookahead() -> None:
    candles = _series(150)
    base = RegimeClassifier().classify(candles[:100])
    poisoned = candles[:100] + [_poisoned_candle(i) for i in range(100, 150)]
    assert RegimeClassifier().classify(poisoned[:100]) == base


def test_market_state_no_lookahead() -> None:
    candles = _series(150)
    engine = FeatureEngine()
    base = engine.compute_state("ETHUSDT", MarketDataHealth.HEALTHY, {Timeframe.H1: candles[:100]})
    poisoned = candles[:100] + [_poisoned_candle(i) for i in range(100, 150)]
    replay = engine.compute_state(
        "ETHUSDT", MarketDataHealth.HEALTHY, {Timeframe.H1: poisoned[:100]}
    )
    assert replay == base


def test_replay_truncated_gives_smaller_timestamp() -> None:
    candles = _series(150)
    engine = FeatureEngine()
    full = engine.compute_state("ETHUSDT", MarketDataHealth.HEALTHY, {Timeframe.H1: candles})
    truncated = engine.compute_state(
        "ETHUSDT", MarketDataHealth.HEALTHY, {Timeframe.H1: candles[:120]}
    )
    assert truncated.timestamp_ms < full.timestamp_ms
    assert truncated.timeframes[Timeframe.H1].close == candles[119].close

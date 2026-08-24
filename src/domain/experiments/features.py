"""Features para ML (PRD §30): causales, sin lookahead. Dominio puro.

La feature en la barra `t` usa solo datos ≤ `t`. La etiqueta `labels[t]` usa
`close[t+1]` (el objetivo a predecir, permitido en aprendizaje supervisado).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from domain.market.candle import Candle
from domain.market.indicators import momentum, realized_volatility, returns, rsi

RSI_PERIOD = 14
MOMENTUM_PERIOD = 10
VOL_WINDOW = 20


@dataclass(frozen=True, slots=True)
class FeatureMatrix:
    indices: tuple[int, ...]
    features: tuple[tuple[float, ...], ...]
    labels: tuple[int, ...]


def build_features(candles: Sequence[Candle]) -> FeatureMatrix:
    closes = [c.close for c in candles]
    rets = returns(closes)
    rsi_series = rsi(closes, RSI_PERIOD)
    mom_series = momentum(closes, MOMENTUM_PERIOD)
    vol_series = realized_volatility(closes, VOL_WINDOW)

    indices: list[int] = []
    features: list[tuple[float, ...]] = []
    labels: list[int] = []
    for t in range(len(candles) - 1):
        r = rets[t]
        rsi_t = rsi_series[t]
        m = mom_series[t]
        v = vol_series[t]
        if r is None or rsi_t is None or m is None or v is None:
            continue
        features.append((r, rsi_t / 50.0 - 1.0, m, v))
        labels.append(1 if closes[t + 1] > closes[t] else 0)
        indices.append(t)
    return FeatureMatrix(tuple(indices), tuple(features), tuple(labels))

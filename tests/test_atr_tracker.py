"""AtrTracker: paridad exacta paper↔replay (Fase 16b).

El tracker incremental debe reproducir vela a vela la serie de ``atr()`` para
garantizar que el paper runner en vivo y el replay determinista calculan el
mismo ATR con la misma versión del algoritmo.
"""

import math
import random

import pytest

from domain.market.candle import Candle
from domain.market.indicators import AtrTracker, atr


def _c(o: float, h: float, lo: float, c: float, ts: int = 0, v: float = 1.0) -> Candle:
    return Candle(timestamp_ms=ts, open=o, high=h, low=lo, close=c, volume=v, turnover=v * c)


def _random_candles(n: int, seed: int = 16) -> list[Candle]:
    rng = random.Random(seed)
    price = 3000.0
    candles = []
    for i in range(n):
        o = price
        drift = rng.uniform(-15, 15)
        c = max(1.0, o + drift)
        h = max(o, c) + rng.uniform(0, 8)
        lo = min(o, c) - rng.uniform(0, 8)
        candles.append(_c(o, h, lo, c, ts=i * 900_000))
        price = c
    return candles


def test_tracker_reproduce_serie_atr_exactamente() -> None:
    candles = _random_candles(250)
    serie = atr(candles, 14)
    tracker = AtrTracker(14)
    for candle, esperado in zip(candles, serie, strict=True):
        valor = tracker.update(candle)
        if esperado is None:
            assert valor is None
        else:
            assert valor is not None
            # Igualdad exacta salvo orden de suma en la siembra (float).
            assert math.isclose(valor, esperado, rel_tol=0, abs_tol=1e-9)


@pytest.mark.parametrize("period", [1, 5, 14])
def test_tracker_warmup_devuelve_none_hasta_period(period: int) -> None:
    candles = _random_candles(period + 3, seed=period)
    tracker = AtrTracker(period)
    valores = [tracker.update(c) for c in candles]
    assert all(v is None for v in valores[:period])
    assert all(v is not None for v in valores[period:])


def test_tracker_constante_igual_a_atr() -> None:
    candles = [_c(100, 110, 90, 100, ts=i) for i in range(30)]
    tracker = AtrTracker(14)
    valores = [tracker.update(c) for c in candles]
    assert valores[13] is None
    assert valores[14] == pytest.approx(20.0)
    assert valores[29] == pytest.approx(20.0)
    assert tracker.value == pytest.approx(20.0)


def test_tracker_value_none_antes_del_warmup() -> None:
    tracker = AtrTracker(14)
    assert tracker.value is None
    tracker.update(_c(100, 110, 90, 100))
    assert tracker.value is None


def test_tracker_rechaza_period_invalido() -> None:
    with pytest.raises(ValueError, match="period"):
        AtrTracker(0)

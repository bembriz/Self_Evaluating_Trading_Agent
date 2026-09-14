"""Indicadores técnicos puros (PRD §15): implementados en stdlib, sin TA-Lib/numpy.

Todas las funciones son causales: el valor en el índice ``i`` depende únicamente de
``values[0..i]`` (o ``candles[0..i]``). El warmup se representa con ``None``.
Convenciones:
- ``ema`` se siembra con la SMA de los primeros ``period`` valores.
- ``rsi``/``atr`` usan suavizado de Wilder y su primer valor en el índice ``period``.
- ``vwap`` es acumulado de sesión sobre la serie recibida.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from domain.market.candle import Candle


def _require_positive_period(period: int) -> None:
    if period <= 0:
        raise ValueError(f"period debe ser > 0: {period}")


def sma(values: Sequence[float], period: int) -> list[float | None]:
    _require_positive_period(period)
    out: list[float | None] = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = sum(values[i - period + 1 : i + 1]) / period
    return out


def ema(values: Sequence[float], period: int) -> list[float | None]:
    _require_positive_period(period)
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    alpha = 2.0 / (period + 1)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = alpha * values[i] + (1.0 - alpha) * prev
        out[i] = prev
    return out


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def rsi(values: Sequence[float], period: int = 14) -> list[float | None]:
    _require_positive_period(period)
    out: list[float | None] = [None] * len(values)
    if len(values) < period + 1:
        return out
    gains = [0.0] * len(values)
    losses = [0.0] * len(values)
    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        if change > 0:
            gains[i] = change
        else:
            losses[i] = -change
    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period
    out[period] = _rsi_value(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i] = _rsi_value(avg_gain, avg_loss)
    return out


@dataclass(frozen=True, slots=True)
class MACDResult:
    macd: list[float | None]
    signal: list[float | None]
    histogram: list[float | None]


def _ema_defined(values: list[float | None], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    defined = [v for v in values if v is not None]
    if len(defined) < period:
        return out
    alpha = 2.0 / (period + 1)
    prev = sum(defined[:period]) / period
    positions = [i for i, v in enumerate(values) if v is not None]
    out[positions[period - 1]] = prev
    for idx, v in zip(positions[period:], defined[period:], strict=True):
        prev = alpha * v + (1.0 - alpha) * prev
        out[idx] = prev
    return out


def macd(values: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9) -> MACDResult:
    _require_positive_period(fast)
    _require_positive_period(slow)
    _require_positive_period(signal)
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    line: list[float | None] = [None] * len(values)
    for i in range(len(values)):
        f = ema_fast[i]
        s = ema_slow[i]
        if f is not None and s is not None:
            line[i] = f - s
    signal_line = _ema_defined(line, signal)
    histogram: list[float | None] = [None] * len(values)
    for i in range(len(values)):
        line_val = line[i]
        signal_val = signal_line[i]
        if line_val is not None and signal_val is not None:
            histogram[i] = line_val - signal_val
    return MACDResult(macd=line, signal=signal_line, histogram=histogram)


def atr(candles: Sequence[Candle], period: int = 14) -> list[float | None]:
    _require_positive_period(period)
    out: list[float | None] = [None] * len(candles)
    if len(candles) < period + 1:
        return out
    trs = [0.0] * len(candles)
    trs[0] = candles[0].high - candles[0].low
    for i in range(1, len(candles)):
        prev_close = candles[i - 1].close
        trs[i] = max(
            candles[i].high - candles[i].low,
            abs(candles[i].high - prev_close),
            abs(candles[i].low - prev_close),
        )
    avg = sum(trs[1 : period + 1]) / period
    out[period] = avg
    for i in range(period + 1, len(candles)):
        avg = (avg * (period - 1) + trs[i]) / period
        out[i] = avg
    return out


class AtrTracker:
    """ATR incremental (Wilder) vela a vela, causal y sin ventana.

    Reproduce exactamente la serie de ``atr()`` (misma siembra SMA de los primeros
    ``period`` TRs y misma recurrencia), permitiendo que el flujo en tiempo real
    obtenga los mismos valores que el replay sobre la serie completa sin mantener
    toda la historia en memoria. Devuelve ``None`` durante el warmup.
    """

    __slots__ = ("_period", "_prev_close", "_seed_trs", "_value")

    def __init__(self, period: int = 14) -> None:
        _require_positive_period(period)
        self._period = period
        self._prev_close: float | None = None
        self._seed_trs: list[float] = []
        self._value: float | None = None

    @property
    def value(self) -> float | None:
        return self._value

    def update(self, candle: Candle) -> float | None:
        if self._prev_close is None:
            self._prev_close = candle.close
            return None
        tr = max(
            candle.high - candle.low,
            abs(candle.high - self._prev_close),
            abs(candle.low - self._prev_close),
        )
        self._prev_close = candle.close
        if self._value is not None:
            self._value = (self._value * (self._period - 1) + tr) / self._period
            return self._value
        self._seed_trs.append(tr)
        if len(self._seed_trs) < self._period:
            return None
        self._value = sum(self._seed_trs) / self._period
        self._seed_trs = []
        return self._value


def vwap(candles: Sequence[Candle]) -> list[float | None]:
    out: list[float | None] = [None] * len(candles)
    cum_pv = 0.0
    cum_volume = 0.0
    for i, c in enumerate(candles):
        typical = (c.high + c.low + c.close) / 3.0
        cum_pv += typical * c.volume
        cum_volume += c.volume
        out[i] = cum_pv / cum_volume if cum_volume > 0 else None
    return out


def returns(values: Sequence[float]) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for i in range(1, len(values)):
        prev = values[i - 1]
        out[i] = (values[i] - prev) / prev if prev != 0 else None
    return out


def realized_volatility(values: Sequence[float], window: int) -> list[float | None]:
    _require_positive_period(window)
    out: list[float | None] = [None] * len(values)
    rets = returns(values)
    for i in range(len(values)):
        start = max(1, i - window + 1)
        window_rets = [r for r in rets[start : i + 1] if r is not None]
        if len(window_rets) >= 2:
            mean = sum(window_rets) / len(window_rets)
            variance = sum((r - mean) ** 2 for r in window_rets) / (len(window_rets) - 1)
            out[i] = variance**0.5
    return out


def momentum(values: Sequence[float], window: int) -> list[float | None]:
    _require_positive_period(window)
    out: list[float | None] = [None] * len(values)
    for i in range(window, len(values)):
        base = values[i - window]
        out[i] = (values[i] - base) / base if base != 0 else None
    return out


def relative_volume(candles: Sequence[Candle], window: int) -> list[float | None]:
    _require_positive_period(window)
    out: list[float | None] = [None] * len(candles)
    for i in range(len(candles)):
        start = max(0, i - window + 1)
        vols = [c.volume for c in candles[start : i + 1]]
        mean = sum(vols) / len(vols)
        out[i] = candles[i].volume / mean if mean > 0 else None
    return out


def adx(candles: Sequence[Candle], period: int = 14) -> list[float | None]:
    """Average Directional Index de Wilder (causal). ``None`` durante warmup.

    TR/+DM/-DM empiezan en el índice 1. El primer suavizado (media de Wilder)
    está en el índice ``period``; el primer DX también. El primer ADX está en el
    índice ``2*period - 1``, sembrado con la media de Wilder de los DX
    ``period..2*period-1``. Después: ``avg = (avg*(period-1) + value)/period``.
    Cada valor en ``i`` depende solo de las velas ``0..i``.
    """
    _require_positive_period(period)
    out: list[float | None] = [None] * len(candles)
    if len(candles) < 2 * period:
        return out

    trs = [0.0] * len(candles)
    plus_dm = [0.0] * len(candles)
    minus_dm = [0.0] * len(candles)
    for i in range(1, len(candles)):
        prev = candles[i - 1]
        cur = candles[i]
        trs[i] = max(
            cur.high - cur.low,
            abs(cur.high - prev.close),
            abs(cur.low - prev.close),
        )
        up = cur.high - prev.high
        down = prev.low - cur.low
        if up > down and up > 0.0:
            plus_dm[i] = up
        elif down > up and down > 0.0:
            minus_dm[i] = down

    smooth_tr = sum(trs[1 : period + 1]) / period
    smooth_plus = sum(plus_dm[1 : period + 1]) / period
    smooth_minus = sum(minus_dm[1 : period + 1]) / period

    dx_sum = 0.0
    dx_count = 0
    adx_value = 0.0
    for i in range(period, len(candles)):
        if i > period:
            smooth_tr = (smooth_tr * (period - 1) + trs[i]) / period
            smooth_plus = (smooth_plus * (period - 1) + plus_dm[i]) / period
            smooth_minus = (smooth_minus * (period - 1) + minus_dm[i]) / period
        if smooth_tr == 0.0:
            plus_di = 0.0
            minus_di = 0.0
        else:
            plus_di = 100.0 * smooth_plus / smooth_tr
            minus_di = 100.0 * smooth_minus / smooth_tr
        denom = plus_di + minus_di
        dx = 100.0 * abs(plus_di - minus_di) / denom if denom != 0.0 else 0.0
        if dx_count < period:
            dx_sum += dx
            dx_count += 1
            if dx_count == period:
                adx_value = dx_sum / period
                out[i] = adx_value
        else:
            adx_value = (adx_value * (period - 1) + dx) / period
            out[i] = adx_value
    return out


@dataclass(frozen=True, slots=True)
class BollingerBands:
    """Bandas de Bollinger en un índice: media, banda superior e inferior."""

    middle: float
    upper: float
    lower: float


def bollinger(
    values: Sequence[float], period: int = 20, multiplier: float = 2.0
) -> list[BollingerBands | None]:
    """Bandas de Bollinger causales con desviación poblacional (``ddof=0``).

    La vela/valor actual se incluye en la ventana. Cada banda en ``i`` depende
    solo de ``values[0..i]``. Primer índice disponible: ``period - 1``.
    """
    _require_positive_period(period)
    if not math.isfinite(multiplier) or multiplier <= 0.0:
        raise ValueError(f"multiplier must be finite and > 0: {multiplier!r}")
    out: list[BollingerBands | None] = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        middle = sum(window) / period
        std = statistics.pstdev(window)
        out[i] = BollingerBands(
            middle=middle,
            upper=middle + multiplier * std,
            lower=middle - multiplier * std,
        )
    return out

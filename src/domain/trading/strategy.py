"""Estrategia baseline determinista y versionada (PRD §29). Dominio puro.

`EmaRsiBaseline` usa trackers incrementales de EMA/RSI con seeds idénticos a
`domain.market.indicators` (SMA para EMA, suavizado de Wilder para RSI). Reglas:
- BUY  si EMA fast cruza por encima de EMA slow (tendencia al alza).
- SELL si EMA fast cruza por debajo de EMA slow o RSI > `rsi_exit` (sobrecompra).
- HOLD en cualquier otro caso (incluido warmup).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domain.market.candle import Candle
from domain.trading.signal import Action, Signal


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


class _EmaTracker:
    def __init__(self, period: int) -> None:
        self._period = period
        self._alpha = 2.0 / (period + 1)
        self._buffer: list[float] = []
        self.prev: float | None = None
        self.current: float | None = None

    def update(self, value: float) -> None:
        if self.current is None:
            self._buffer.append(value)
            if len(self._buffer) == self._period:
                self.current = sum(self._buffer) / self._period
        else:
            self.prev = self.current
            self.current = self._alpha * value + (1.0 - self._alpha) * self.current


class _RsiTracker:
    def __init__(self, period: int) -> None:
        self._period = period
        self._changes: list[tuple[float, float]] = []
        self._prev_close: float | None = None
        self.avg_gain: float | None = None
        self.avg_loss: float | None = None
        self.prev: float | None = None
        self.current: float | None = None

    def update(self, close: float) -> None:
        if self._prev_close is None:
            self._prev_close = close
            return
        change = close - self._prev_close
        self._prev_close = close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = self.avg_gain
        avg_loss = self.avg_loss
        if avg_gain is None or avg_loss is None:
            self._changes.append((gain, loss))
            if len(self._changes) == self._period:
                avg_gain = sum(g for g, _ in self._changes) / self._period
                avg_loss = sum(lo for _, lo in self._changes) / self._period
                self.avg_gain = avg_gain
                self.avg_loss = avg_loss
                self.current = _rsi_value(avg_gain, avg_loss)
        else:
            self.prev = self.current
            avg_gain = (avg_gain * (self._period - 1) + gain) / self._period
            avg_loss = (avg_loss * (self._period - 1) + loss) / self._period
            self.avg_gain = avg_gain
            self.avg_loss = avg_loss
            self.current = _rsi_value(avg_gain, avg_loss)


class Strategy(Protocol):
    version: str

    def on_candle(self, candle: Candle) -> Signal: ...


@dataclass(frozen=True, slots=True)
class EmaRsiConfig:
    ema_fast: int = 20
    ema_slow: int = 50
    rsi_period: int = 14
    rsi_exit: float = 80.0


class EmaRsiBaseline:
    version = "baseline-v1"

    def __init__(self, config: EmaRsiConfig | None = None) -> None:
        self._config = config or EmaRsiConfig()
        self._fast = _EmaTracker(self._config.ema_fast)
        self._slow = _EmaTracker(self._config.ema_slow)
        self._rsi = _RsiTracker(self._config.rsi_period)

    def on_candle(self, candle: Candle) -> Signal:
        close = candle.close
        self._fast.update(close)
        self._slow.update(close)
        self._rsi.update(close)
        timestamp_ms = candle.timestamp_ms
        f_prev, f_cur = self._fast.prev, self._fast.current
        s_prev, s_cur = self._slow.prev, self._slow.current
        rsi = self._rsi.current
        if f_prev is None or f_cur is None or s_prev is None or s_cur is None or rsi is None:
            return Signal(timestamp_ms, Action.HOLD, reason="warmup")
        crossed_up = f_prev <= s_prev and f_cur > s_cur
        crossed_down = f_prev >= s_prev and f_cur < s_cur
        if crossed_up:
            return Signal(timestamp_ms, Action.BUY, reason="ema_cross_up")
        if crossed_down or rsi > self._config.rsi_exit:
            return Signal(timestamp_ms, Action.SELL, reason="ema_cross_down_or_rsi_exit")
        return Signal(timestamp_ms, Action.HOLD)

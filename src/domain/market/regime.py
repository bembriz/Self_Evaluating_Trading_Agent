"""Clasificación determinista y versionada del régimen de mercado (PRD §16).

Estados: TREND_UP, TREND_DOWN, SIDEWAYS, HIGH_VOLATILITY, LOW_VOLATILITY, BREAKOUT.
La implementación es causal (solo usa la vela corriente y las anteriores) y lleva una
versión explícita para reproducibilidad.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from domain.market.candle import Candle
from domain.market.indicators import ema, realized_volatility


class MarketRegime(StrEnum):
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    SIDEWAYS = "sideways"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    BREAKOUT = "breakout"


@dataclass(frozen=True, slots=True)
class RegimeConfig:
    ema_fast: int = 20
    ema_slow: int = 50
    vol_window: int = 20
    vol_baseline: int = 100
    breakout_lookback: int = 20
    high_vol_threshold: float = 1.5
    low_vol_threshold: float = 0.5
    trend_threshold: float = 0.005


class RegimeClassifier:
    """Clasificador determinista. ``version`` identifica la regla para experimentos."""

    version = "regime-v1"

    def __init__(self, config: RegimeConfig | None = None) -> None:
        self._config = config or RegimeConfig()

    def classify(self, candles: Sequence[Candle]) -> MarketRegime | None:
        if len(candles) < 2:
            return None
        cfg = self._config
        if self._is_breakout(candles, cfg):
            return MarketRegime.BREAKOUT
        vol_ratio = self._volatility_ratio(candles, cfg)
        if vol_ratio is not None:
            if vol_ratio >= cfg.high_vol_threshold:
                return MarketRegime.HIGH_VOLATILITY
            if vol_ratio <= cfg.low_vol_threshold:
                return MarketRegime.LOW_VOLATILITY
        trend = self._trend(candles, cfg)
        if trend is not None:
            if trend > cfg.trend_threshold:
                return MarketRegime.TREND_UP
            if trend < -cfg.trend_threshold:
                return MarketRegime.TREND_DOWN
        return MarketRegime.SIDEWAYS

    @staticmethod
    def _is_breakout(candles: Sequence[Candle], cfg: RegimeConfig) -> bool:
        lookback = cfg.breakout_lookback
        start = max(0, len(candles) - lookback - 1)
        prior = list(candles)[start:-1]
        if not prior:
            return False
        last = candles[-1]
        return last.close > max(c.high for c in prior) or last.close < min(c.low for c in prior)

    @staticmethod
    def _volatility_ratio(candles: Sequence[Candle], cfg: RegimeConfig) -> float | None:
        closes = [c.close for c in candles]
        vol = realized_volatility(closes, cfg.vol_window)
        vol_now = vol[-1]
        if vol_now is None:
            return None
        baseline_end = len(candles)
        baseline_start = max(0, baseline_end - cfg.vol_baseline)
        baseline_window = [v for v in vol[baseline_start:baseline_end] if v is not None]
        if len(baseline_window) < 2:
            return 1.0
        baseline = sum(baseline_window) / len(baseline_window)
        if baseline == 0:
            # vol_now ∈ baseline_window y es >= 0 ⇒ vol_now == 0 ⇒ ratio neutro.
            return 1.0
        return vol_now / baseline

    @staticmethod
    def _trend(candles: Sequence[Candle], cfg: RegimeConfig) -> float | None:
        closes = [c.close for c in candles]
        fast = ema(closes, cfg.ema_fast)[-1]
        slow = ema(closes, cfg.ema_slow)[-1]
        if fast is None or slow is None or slow == 0:
            return None
        return (fast - slow) / slow

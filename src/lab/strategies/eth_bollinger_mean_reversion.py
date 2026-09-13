"""Standalone ETH Bollinger mean-reversion strategy (Phase 20A).

Hypothesis: short-horizon mean reversion in non-trending markets. A BUY requires
a close below the lower Bollinger band followed by a re-entry into the band while
ADX indicates low directional trend strength. The exit is the middle band. SELL
takes precedence over BUY and is independent of ADX.

This strategy does not compose any historical strategy and does not track
portfolio position; the RiskEngine and PaperEngine remain authoritative.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from domain.market.candle import Candle
from domain.market.indicators import adx, bollinger
from domain.trading.signal import Action, Signal
from lab.fingerprints import StrategyDefinition
from lab.frozen_dataset import FrozenDatasetAdapter


@dataclass(frozen=True, slots=True)
class EthBollingerMeanReversionConfig:
    """Frozen Bollinger and ADX parameters for the mean-reversion strategy."""

    bollinger_period: int = 20
    bollinger_stddev_multiplier: float = 2.0
    adx_period: int = 14
    adx_max: float = 20.0


class EthBollingerMeanReversion:
    """Bollinger excursion/re-entry entry gated by a low-ADX regime."""

    strategy_name = "EthBollingerMeanReversion"
    version = "eth-bollinger-mean-reversion-v1"

    def __init__(
        self,
        *,
        candles: Sequence[Candle],
        config: EthBollingerMeanReversionConfig | None = None,
    ) -> None:
        self._config = config or EthBollingerMeanReversionConfig()
        if self._config.adx_period < 1:
            raise ValueError("adx_period must be positive")
        if not math.isfinite(self._config.adx_max) or self._config.adx_max < 0.0:
            raise ValueError("adx_max must be finite and non-negative")

        prepared = tuple(candles)
        if not prepared:
            raise ValueError("candles must be non-empty")
        closes = [candle.close for candle in prepared]
        self._bands = bollinger(
            closes,
            self._config.bollinger_period,
            self._config.bollinger_stddev_multiplier,
        )
        self._adx = adx(prepared, self._config.adx_period)
        self._candles = prepared
        self._index = 0

    @classmethod
    def from_adapters(
        cls,
        *,
        adapter: FrozenDatasetAdapter,
        config: EthBollingerMeanReversionConfig | None = None,
    ) -> EthBollingerMeanReversion:
        """Construct from a frozen DEVELOPMENT dataset adapter."""
        return cls(candles=adapter.candles, config=config)

    def on_candle(self, candle: Candle) -> Signal:
        """Return SELL at/above the middle band, BUY on a low-ADX re-entry, else HOLD."""
        if self._index >= len(self._candles):
            raise ValueError("preloaded candle sequence exhausted")
        expected = self._candles[self._index]
        if candle != expected:
            raise ValueError("runner candle does not match preloaded sequence")

        index = self._index
        self._index += 1
        current = self._bands[index]

        # STEP 1 — SELL has absolute strategy-level precedence and ignores ADX.
        if current is not None and candle.close >= current.middle:
            return Signal(
                timestamp_ms=candle.timestamp_ms,
                action=Action.SELL,
                reason="bollinger_middle_exit",
            )

        # STEP 2 — BUY only if SELL did not trigger.
        if index >= 1:
            previous = self._bands[index - 1]
            adx_value = self._adx[index]
            if (
                previous is not None
                and current is not None
                and adx_value is not None
                and self._candles[index - 1].close < previous.lower
                and candle.close >= current.lower
                and adx_value < self._config.adx_max
            ):
                return Signal(
                    timestamp_ms=candle.timestamp_ms,
                    action=Action.BUY,
                    reason="bollinger_reentry_low_adx",
                )

        # STEP 3
        return Signal(timestamp_ms=candle.timestamp_ms, action=Action.HOLD)


def strategy_definition(
    config: EthBollingerMeanReversionConfig | None = None,
) -> StrategyDefinition:
    """Declare the strategy source/config using the existing identity contract."""
    candidate_config = config or EthBollingerMeanReversionConfig()
    return StrategyDefinition(
        strategy_id=EthBollingerMeanReversion.strategy_name,
        strategy_version=EthBollingerMeanReversion.version,
        kind="deterministic",
        normalized_config={
            "bollinger_period": candidate_config.bollinger_period,
            "bollinger_stddev_multiplier": candidate_config.bollinger_stddev_multiplier,
            "adx_period": candidate_config.adx_period,
            "adx_max": candidate_config.adx_max,
        },
        sources=(
            "lab.strategies.eth_bollinger_mean_reversion",
            "domain.market.indicators",
        ),
    )

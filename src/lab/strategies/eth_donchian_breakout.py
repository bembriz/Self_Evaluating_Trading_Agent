"""Standalone ETH Donchian breakout strategy with a causal ADX trend gate.

BUY:  close[t] > max(high[t-entry:t])  AND  adx14[t] > adx_min
SELL: close[t] < min(low[t-exit:t])

The current candle is strictly excluded from both Donchian windows. ADX
readiness affects BUY only; SELL is independent of ADX. The strategy does not
compose `EmaRsiBaseline` and does not track position state (the RiskEngine and
PaperEngine retain authority).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from domain.market.candle import Candle
from domain.market.indicators import adx
from domain.trading.signal import Action, Signal
from lab.fingerprints import StrategyDefinition
from lab.frozen_dataset import FrozenDatasetAdapter


@dataclass(frozen=True, slots=True)
class EthDonchianBreakoutConfig:
    """Frozen Donchian and ADX parameters for the breakout strategy."""

    entry_donchian_lookback: int = 20
    exit_donchian_lookback: int = 10
    adx_period: int = 14
    adx_min: float = 20.0


class EthDonchianBreakout:
    """Close-based Donchian breakout gated by a causal Wilder ADX."""

    strategy_name = "EthDonchianBreakout"
    version = "eth-donchian-breakout-v1"

    def __init__(
        self,
        *,
        candles: Sequence[Candle],
        config: EthDonchianBreakoutConfig | None = None,
    ) -> None:
        self._config = config or EthDonchianBreakoutConfig()
        entry = self._config.entry_donchian_lookback
        exit_lookback = self._config.exit_donchian_lookback
        period = self._config.adx_period
        if entry < 1 or exit_lookback < 1 or period < 1:
            raise ValueError("lookbacks and adx period must be positive")
        if self._config.adx_min < 0.0:
            raise ValueError("adx_min must be non-negative")

        prepared = tuple(candles)
        if not prepared:
            raise ValueError("candles must be non-empty")
        highs = [candle.high for candle in prepared]
        lows = [candle.low for candle in prepared]
        prior_high: list[float | None] = [None] * len(prepared)
        prior_low: list[float | None] = [None] * len(prepared)
        for index in range(len(prepared)):
            if index >= entry:
                prior_high[index] = max(highs[index - entry : index])
            if index >= exit_lookback:
                prior_low[index] = min(lows[index - exit_lookback : index])
        self._candles = prepared
        self._prior_high = prior_high
        self._prior_low = prior_low
        self._adx = adx(prepared, period)
        self._index = 0

    @classmethod
    def from_adapters(
        cls,
        *,
        adapter: FrozenDatasetAdapter,
        config: EthDonchianBreakoutConfig | None = None,
    ) -> EthDonchianBreakout:
        """Construct from a frozen DEVELOPMENT dataset adapter."""
        return cls(candles=adapter.candles, config=config)

    def on_candle(self, candle: Candle) -> Signal:
        """Return BUY on a gated breakout, SELL on a breakdown, else HOLD."""
        if self._index >= len(self._candles):
            raise ValueError("preloaded candle sequence exhausted")
        expected = self._candles[self._index]
        if candle != expected:
            raise ValueError("runner candle does not match preloaded sequence")

        index = self._index
        self._index += 1
        prior_high = self._prior_high[index]
        prior_low = self._prior_low[index]
        adx_value = self._adx[index]
        if (
            prior_high is not None
            and adx_value is not None
            and candle.close > prior_high
            and adx_value > self._config.adx_min
        ):
            return Signal(
                timestamp_ms=candle.timestamp_ms,
                action=Action.BUY,
                reason="donchian_breakout_adx",
            )
        if prior_low is not None and candle.close < prior_low:
            return Signal(
                timestamp_ms=candle.timestamp_ms,
                action=Action.SELL,
                reason="donchian_exit",
            )
        return Signal(timestamp_ms=candle.timestamp_ms, action=Action.HOLD)


def strategy_definition(
    config: EthDonchianBreakoutConfig | None = None,
) -> StrategyDefinition:
    """Declare the strategy source/config using the existing identity contract."""
    candidate_config = config or EthDonchianBreakoutConfig()
    return StrategyDefinition(
        strategy_id=EthDonchianBreakout.strategy_name,
        strategy_version=EthDonchianBreakout.version,
        kind="deterministic",
        normalized_config={
            "entry_donchian_lookback": candidate_config.entry_donchian_lookback,
            "exit_donchian_lookback": candidate_config.exit_donchian_lookback,
            "adx_period": candidate_config.adx_period,
            "adx_min": candidate_config.adx_min,
        },
        sources=(
            "lab.strategies.eth_donchian_breakout",
            "domain.market.indicators",
        ),
    )

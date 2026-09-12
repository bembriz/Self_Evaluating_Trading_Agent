"""EMA/RSI baseline candidate with a causal BTC trend gate on ETH BUYs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from domain.market.candle import Candle
from domain.market.indicators import ema
from domain.trading.signal import Action, Signal
from domain.trading.strategy import EmaRsiBaseline, EmaRsiConfig
from lab.fingerprints import StrategyDefinition
from lab.frozen_dataset import FrozenDatasetAdapter


@dataclass(frozen=True, slots=True)
class EmaRsiBtcContextConfig:
    """Frozen ETH baseline and BTC context parameters for candidate v1."""

    ema_fast: int = 20
    ema_slow: int = 50
    rsi_period: int = 14
    rsi_exit: float = 80.0
    btc_ema_fast: int = 20
    btc_ema_slow: int = 50


class EmaRsiBtcContext:
    """Filter baseline ETH BUY candidates with aligned BTC EMA context."""

    strategy_name = "EmaRsiBtcContext"
    version = "ema-rsi-btc-context-v1"

    def __init__(
        self,
        *,
        primary_candles: Sequence[Candle],
        btc_candles: Sequence[Candle],
        config: EmaRsiBtcContextConfig | None = None,
    ) -> None:
        self._config = config or EmaRsiBtcContextConfig()
        periods = (
            self._config.ema_fast,
            self._config.ema_slow,
            self._config.rsi_period,
            self._config.btc_ema_fast,
            self._config.btc_ema_slow,
        )
        if min(periods) <= 0:
            raise ValueError("indicator periods must be positive")
        if self._config.ema_fast >= self._config.ema_slow:
            raise ValueError("ETH EMA fast period must be less than slow period")
        if self._config.btc_ema_fast >= self._config.btc_ema_slow:
            raise ValueError("BTC EMA fast period must be less than slow period")

        primary = tuple(primary_candles)
        context = tuple(btc_candles)
        if not primary:
            raise ValueError("aligned ETH/BTC candles must be non-empty")
        if len(primary) != len(context):
            raise ValueError("ETH/BTC candle length mismatch")
        for index, (eth_candle, btc_candle) in enumerate(zip(primary, context, strict=True)):
            if eth_candle.timestamp_ms != btc_candle.timestamp_ms:
                raise ValueError(f"ETH/BTC timestamp mismatch at row {index}")

        btc_closes = [candle.close for candle in context]
        btc_fast = ema(btc_closes, self._config.btc_ema_fast)
        btc_slow = ema(btc_closes, self._config.btc_ema_slow)
        self._btc_bullish = tuple(
            None if fast is None or slow is None else fast > slow
            for fast, slow in zip(btc_fast, btc_slow, strict=True)
        )
        self._primary = primary
        self._baseline = EmaRsiBaseline(
            EmaRsiConfig(
                ema_fast=self._config.ema_fast,
                ema_slow=self._config.ema_slow,
                rsi_period=self._config.rsi_period,
                rsi_exit=self._config.rsi_exit,
            )
        )
        self._index = 0

    @classmethod
    def from_adapters(
        cls,
        *,
        primary: FrozenDatasetAdapter,
        context: FrozenDatasetAdapter,
        config: EmaRsiBtcContextConfig | None = None,
    ) -> EmaRsiBtcContext:
        """Construct from matching frozen DEVELOPMENT dataset adapters."""
        primary_range = primary.range
        context_range = context.range
        if (
            primary_range.symbol,
            primary_range.timeframe,
            primary_range.row_start,
            primary_range.row_end,
        ) != ("ETHUSDT", "15m", context_range.row_start, context_range.row_end):
            raise ValueError("primary adapter must be aligned ETHUSDT 15m")
        if (
            context_range.dataset_id,
            context_range.symbol,
            context_range.timeframe,
            context_range.manifest_sha,
        ) != (
            primary_range.dataset_id,
            "BTCUSDT",
            "15m",
            primary_range.manifest_sha,
        ):
            raise ValueError("context adapter must be aligned BTCUSDT 15m from same dataset")
        return cls(
            primary_candles=primary.candles,
            btc_candles=context.candles,
            config=config,
        )

    def on_candle(self, candle: Candle) -> Signal:
        """Return baseline signal, filtering only BUY candidates with BTC context."""
        if self._index >= len(self._primary):
            raise ValueError("preloaded ETH sequence exhausted")
        expected = self._primary[self._index]
        if candle != expected:
            raise ValueError("runner candle does not match preloaded ETH sequence")

        baseline_signal = self._baseline.on_candle(candle)
        btc_bullish = self._btc_bullish[self._index]
        self._index += 1
        if baseline_signal.action is not Action.BUY:
            return baseline_signal
        if btc_bullish is True:
            return Signal(
                timestamp_ms=baseline_signal.timestamp_ms,
                action=Action.BUY,
                intensity=baseline_signal.intensity,
                reason="ema_cross_up_btc_confirmed",
            )
        return Signal(
            timestamp_ms=baseline_signal.timestamp_ms,
            action=Action.HOLD,
            intensity=baseline_signal.intensity,
            reason="btc_context_block",
        )


def strategy_definition(
    config: EmaRsiBtcContextConfig | None = None,
) -> StrategyDefinition:
    """Declare candidate source/config using the existing Phase 17B identity contract."""
    candidate_config = config or EmaRsiBtcContextConfig()
    return StrategyDefinition(
        strategy_id=EmaRsiBtcContext.strategy_name,
        strategy_version=EmaRsiBtcContext.version,
        kind="deterministic",
        normalized_config={
            "ema_fast": candidate_config.ema_fast,
            "ema_slow": candidate_config.ema_slow,
            "rsi_period": candidate_config.rsi_period,
            "rsi_exit": candidate_config.rsi_exit,
            "btc_ema_fast": candidate_config.btc_ema_fast,
            "btc_ema_slow": candidate_config.btc_ema_slow,
        },
        sources=(
            "lab.strategies.ema_rsi_btc_context",
            "domain.trading.strategy",
            "domain.market.indicators",
        ),
    )

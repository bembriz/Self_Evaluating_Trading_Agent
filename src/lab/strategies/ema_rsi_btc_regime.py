"""EMA/RSI baseline candidate with a causal BTC trend+slope regime gate on ETH BUYs."""

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
class EmaRsiBtcRegimeConfig:
    """Frozen ETH baseline and BTC trend+slope context parameters."""

    ema_fast: int = 20
    ema_slow: int = 50
    rsi_period: int = 14
    rsi_exit: float = 80.0
    btc_ema_fast: int = 20
    btc_ema_slow: int = 50
    btc_slope_lookback: int = 4


class EmaRsiBtcRegime:
    """Filter baseline ETH BUY candidates with a causal BTC trend+slope regime.

    `BTC_RISK_ON[t] = EMA20[t] > EMA50[t] AND EMA20[t] > EMA20[t-4]`. The second
    comparison is a positive EMA slope/direction, not quantitative acceleration.
    """

    strategy_name = "EmaRsiBtcRegime"
    version = "ema-rsi-btc-regime-v1"

    def __init__(
        self,
        *,
        primary_candles: Sequence[Candle],
        btc_candles: Sequence[Candle],
        config: EmaRsiBtcRegimeConfig | None = None,
    ) -> None:
        self._config = config or EmaRsiBtcRegimeConfig()
        periods = (
            self._config.ema_fast,
            self._config.ema_slow,
            self._config.rsi_period,
            self._config.btc_ema_fast,
            self._config.btc_ema_slow,
        )
        if min(periods) <= 0:
            raise ValueError("indicator periods must be positive")
        if self._config.btc_slope_lookback < 1:
            raise ValueError("btc_slope_lookback must be positive")
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
        lookback = self._config.btc_slope_lookback
        risk_on: list[bool] = []
        for index in range(len(btc_closes)):
            fast = btc_fast[index]
            slow = btc_slow[index]
            lag_index = index - lookback
            lag = btc_fast[lag_index] if lag_index >= 0 else None
            if fast is None or slow is None or lag is None:
                risk_on.append(False)
            else:
                risk_on.append(bool(fast > slow and fast > lag))
        self._btc_risk_on = tuple(risk_on)
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
        config: EmaRsiBtcRegimeConfig | None = None,
    ) -> EmaRsiBtcRegime:
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
        """Return baseline signal, filtering only BUY candidates with BTC regime."""
        if self._index >= len(self._primary):
            raise ValueError("preloaded ETH sequence exhausted")
        expected = self._primary[self._index]
        if candle != expected:
            raise ValueError("runner candle does not match preloaded ETH sequence")

        baseline_signal = self._baseline.on_candle(candle)
        risk_on = self._btc_risk_on[self._index]
        self._index += 1
        if baseline_signal.action is not Action.BUY:
            return baseline_signal
        if risk_on:
            return Signal(
                timestamp_ms=baseline_signal.timestamp_ms,
                action=Action.BUY,
                intensity=baseline_signal.intensity,
                reason="ema_cross_up_btc_regime_confirmed",
            )
        return Signal(
            timestamp_ms=baseline_signal.timestamp_ms,
            action=Action.HOLD,
            intensity=baseline_signal.intensity,
            reason="btc_regime_block",
        )


def strategy_definition(
    config: EmaRsiBtcRegimeConfig | None = None,
) -> StrategyDefinition:
    """Declare candidate source/config using the existing identity contract."""
    candidate_config = config or EmaRsiBtcRegimeConfig()
    return StrategyDefinition(
        strategy_id=EmaRsiBtcRegime.strategy_name,
        strategy_version=EmaRsiBtcRegime.version,
        kind="deterministic",
        normalized_config={
            "ema_fast": candidate_config.ema_fast,
            "ema_slow": candidate_config.ema_slow,
            "rsi_period": candidate_config.rsi_period,
            "rsi_exit": candidate_config.rsi_exit,
            "btc_ema_fast": candidate_config.btc_ema_fast,
            "btc_ema_slow": candidate_config.btc_ema_slow,
            "btc_slope_lookback": candidate_config.btc_slope_lookback,
        },
        sources=(
            "lab.strategies.ema_rsi_btc_regime",
            "domain.trading.strategy",
            "domain.market.indicators",
        ),
    )

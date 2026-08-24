import pytest

from domain.market.candle import Candle, Timeframe
from domain.market.feature_engine import FeatureEngine, FeatureEngineConfig
from domain.market.orderbook import MarketDataHealth
from domain.market.regime import MarketRegime


def _c(ts: int, o: float, h: float, lo: float, c: float, v: float = 1.0) -> Candle:
    return Candle(timestamp_ms=ts, open=o, high=h, low=lo, close=c, volume=v, turnover=v * c)


def _series(n: int, start: float = 100.0) -> list[Candle]:
    out: list[Candle] = []
    prev = start
    for i in range(n):
        close = prev * 1.002
        out.append(_c(i * 3600_000, prev, close + 5, prev - 5, close))
        prev = close
    return out


def test_computes_timeframe_features() -> None:
    candles = _series(200)
    state = FeatureEngine().compute_state(
        "ETHUSDT", MarketDataHealth.HEALTHY, {Timeframe.H1: candles}
    )
    assert state.symbol == "ETHUSDT"
    assert state.health is MarketDataHealth.HEALTHY
    tf = state.timeframes[Timeframe.H1]
    assert tf.close == pytest.approx(candles[-1].close)
    assert tf.rsi is not None
    assert tf.atr is not None
    assert tf.macd is not None
    assert tf.vwap is not None


def test_timestamp_is_max_across_timeframes() -> None:
    state = FeatureEngine().compute_state(
        "ETHUSDT",
        MarketDataHealth.HEALTHY,
        {Timeframe.M15: _series(50), Timeframe.H1: _series(10)},
    )
    assert state.timestamp_ms == 49 * 3600_000


def test_regime_from_default_timeframe() -> None:
    state = FeatureEngine().compute_state(
        "ETHUSDT",
        MarketDataHealth.HEALTHY,
        {Timeframe.M15: _series(200), Timeframe.H1: _series(120)},
    )
    assert state.regime is MarketRegime.TREND_UP


def test_regime_falls_back_to_longest_timeframe() -> None:
    state = FeatureEngine().compute_state(
        "ETHUSDT",
        MarketDataHealth.HEALTHY,
        {Timeframe.M15: _series(120)},
    )
    assert state.regime is MarketRegime.TREND_UP


def test_btc_context_read_only() -> None:
    state = FeatureEngine().compute_state(
        "ETHUSDT",
        MarketDataHealth.HEALTHY,
        {Timeframe.H1: _series(120)},
        btc_candles=_series(120, start=30000.0),
    )
    assert state.btc is not None
    assert state.btc.symbol == "BTCUSDT"
    assert state.btc.close is not None
    assert state.btc.rsi is not None


def test_orderbook_passed_through() -> None:
    from domain.market.features import OrderBookFeatureSnapshot

    snapshot = OrderBookFeatureSnapshot(
        symbol="ETHUSDT",
        window_start_ms=0,
        window_end_ms=1000,
        best_bid=100.0,
        best_ask=101.0,
        spread=1.0,
        spread_pct=0.01,
        bid_depth=10.0,
        ask_depth=8.0,
        imbalance=10.0 / 18.0,
    )
    state = FeatureEngine().compute_state(
        "ETHUSDT",
        MarketDataHealth.HEALTHY,
        {Timeframe.H1: _series(120)},
        orderbook=snapshot,
    )
    assert state.orderbook is snapshot


def test_empty_input() -> None:
    state = FeatureEngine().compute_state("ETHUSDT", MarketDataHealth.STALE, {})
    assert state.timestamp_ms == 0
    assert state.regime is None
    assert state.timeframes == {}
    assert state.btc is None


def test_config_exposes_regime_timeframe() -> None:
    cfg = FeatureEngineConfig()
    assert cfg.regime_timeframe is Timeframe.H1

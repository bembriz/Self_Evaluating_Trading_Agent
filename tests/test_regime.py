from collections import deque

from domain.market.candle import Candle
from domain.market.regime import MarketRegime, RegimeClassifier, RegimeConfig


def _c(ts: int, o: float, h: float, lo: float, c: float, v: float = 1.0) -> Candle:
    return Candle(timestamp_ms=ts, open=o, high=h, low=lo, close=c, volume=v, turnover=v * c)


def _uptrend(n: int = 120, start: float = 100.0) -> list[Candle]:
    out: list[Candle] = []
    prev = start
    for i in range(n):
        close = prev * 1.002
        out.append(_c(i, prev, close + 5, prev - 5, close))
        prev = close
    return out


def _downtrend(n: int = 120, start: float = 200.0) -> list[Candle]:
    out: list[Candle] = []
    prev = start
    for i in range(n):
        close = prev * 0.998
        out.append(_c(i, prev, prev + 5, close - 5, close))
        prev = close
    return out


def test_classifier_versioned() -> None:
    assert RegimeClassifier().version == "regime-v1"


def test_not_enough_data_returns_none() -> None:
    assert RegimeClassifier().classify([_c(0, 100, 100, 100, 100)]) is None


def test_uptrend() -> None:
    assert RegimeClassifier().classify(_uptrend()) is MarketRegime.TREND_UP


def test_downtrend() -> None:
    assert RegimeClassifier().classify(_downtrend()) is MarketRegime.TREND_DOWN


def test_breakout_priority() -> None:
    flat = [_c(i, 100, 101, 99, 100) for i in range(60)]
    flat.append(_c(60, 100, 130, 100, 130))
    assert RegimeClassifier().classify(flat) is MarketRegime.BREAKOUT


def test_high_volatility() -> None:
    calm = [
        _c(i, 100 + i * 0.1, 100 + i * 0.1 + 1, 100 + i * 0.1 - 1, 100 + (i + 1) * 0.1)
        for i in range(120)
    ]
    base = 100 + 120 * 0.1
    wild = [
        _c(
            120 + j,
            base + (j % 2) * 10,
            base + (j % 2) * 10 + 1,
            base + (j % 2) * 10 - 1,
            base + (j % 2) * 10,
        )
        for j in range(20)
    ]
    cfg = RegimeConfig(vol_baseline=60)
    assert RegimeClassifier(cfg).classify(calm + wild) is MarketRegime.HIGH_VOLATILITY


def test_low_volatility() -> None:
    wild = [
        _c(i, 100, 100 + (i % 2) * 10, 100 - (i % 2) * 10, 100 + (i % 2) * 10) for i in range(120)
    ]
    calm = [_c(120 + j, 100, 100.5, 99.5, 100) for j in range(20)]
    cfg = RegimeConfig(vol_baseline=60)
    assert RegimeClassifier(cfg).classify(wild + calm) is MarketRegime.LOW_VOLATILITY


def test_sideways() -> None:
    flat = [_c(i, 100, 101, 99, 100) for i in range(120)]
    assert RegimeClassifier().classify(flat) is MarketRegime.SIDEWAYS


def test_two_candles_not_enough_for_features() -> None:
    assert (
        RegimeClassifier().classify([_c(0, 100, 100, 100, 100), _c(1, 100, 100, 100, 100)])
        is MarketRegime.SIDEWAYS
    )


def test_small_baseline_window_returns_neutral() -> None:
    candles = [_c(i, 100, 101, 99, 100) for i in range(30)]
    assert RegimeClassifier(RegimeConfig(vol_baseline=1)).classify(candles) is MarketRegime.SIDEWAYS


def test_zero_lookback_never_breaks_out() -> None:
    candles = [_c(i, 100, 101, 99, 100) for i in range(60)]
    cfg = RegimeConfig(breakout_lookback=0)
    assert RegimeClassifier(cfg).classify(candles) is MarketRegime.SIDEWAYS


def test_classify_accepts_deque_input() -> None:
    assert RegimeClassifier().classify(deque(_uptrend(60))) is MarketRegime.TREND_UP

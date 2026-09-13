import math

import pytest

from domain.market.candle import Candle
from domain.market.indicators import (
    adx,
    atr,
    bollinger,
    ema,
    macd,
    momentum,
    realized_volatility,
    relative_volume,
    returns,
    rsi,
    sma,
    vwap,
)


def _c(o: float, h: float, lo: float, c: float, v: float = 1.0) -> Candle:
    return Candle(timestamp_ms=0, open=o, high=h, low=lo, close=c, volume=v, turnover=v * c)


def test_sma_warmup_and_values() -> None:
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = sma(vals, 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(2.0)
    assert out[4] == pytest.approx(4.0)


def test_ema_seeded_with_sma() -> None:
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = ema(vals, 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(2.0)
    assert out[3] == pytest.approx(3.0)


def test_rsi_flat_is_50_uptrend_is_100() -> None:
    flat = [10.0] * 20
    assert rsi(flat, 14)[14] == pytest.approx(50.0)
    up = [float(i) for i in range(30)]
    assert rsi(up, 14)[14] == pytest.approx(100.0)


def test_rsi_downtrend_is_0() -> None:
    down = [float(30 - i) for i in range(30)]
    assert rsi(down, 14)[14] == pytest.approx(0.0)


def test_macd_histogram_equals_macd_minus_signal() -> None:
    vals = [float(i) for i in range(1, 100)]
    m = macd(vals, 12, 26, 9)
    assert len(m.macd) == len(vals)
    for i in range(len(vals)):
        macd_val = m.macd[i]
        signal_val = m.signal[i]
        if macd_val is not None and signal_val is not None:
            assert m.histogram[i] == pytest.approx(macd_val - signal_val)


def test_atr_constant_range() -> None:
    candles = [_c(100, 110, 90, 100) for _ in range(30)]
    out = atr(candles, 14)
    assert out[14] == pytest.approx(20.0)
    assert out[29] == pytest.approx(20.0)


def test_vwap_cumulative() -> None:
    candles = [
        _c(100, 100, 100, 100, v=2.0),
        _c(100, 110, 100, 110, v=2.0),
    ]
    out = vwap(candles)
    assert out[1] == pytest.approx(413.3333 / 4.0)


def test_returns_and_momentum() -> None:
    vals = [10.0, 11.0, 12.1]
    assert returns(vals)[0] is None
    assert returns(vals)[1] == pytest.approx(0.1)
    assert momentum(vals, 2)[2] == pytest.approx(0.21)


def test_realized_volatility_requires_two_returns() -> None:
    out = realized_volatility([10.0, 11.0, 12.0], 3)
    assert out[0] is None
    assert out[1] is None
    assert out[2] is not None


def test_relative_volume() -> None:
    candles = [_c(100, 100, 100, 100, v=v) for v in (10.0, 10.0, 20.0)]
    out = relative_volume(candles, 3)
    assert out[2] == pytest.approx(20.0 / (40.0 / 3.0))


def test_invalid_period_raises() -> None:
    with pytest.raises(ValueError):
        sma([1.0, 2.0], 0)


def _trend_candles(count: int) -> list[Candle]:
    return [_c(100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i) for i in range(count)]


def test_adx_first_index_is_27_for_period_14() -> None:
    out = adx(_trend_candles(30), 14)
    assert out[26] is None
    assert out[27] is not None


def test_adx_values_before_first_index_are_none() -> None:
    out = adx(_trend_candles(30), 14)
    assert out[:27] == [None] * 27


def test_adx_insufficient_history_returns_all_none() -> None:
    out = adx(_trend_candles(20), 14)
    assert out == [None] * 20


def test_adx_downtrend_is_strong() -> None:
    down = [_c(100.0 - i, 101.0 - i, 99.0 - i, 100.5 - i) for i in range(30)]
    out = adx(down, 14)
    assert out[27] is not None
    assert out[27] > 20.0


def test_adx_monotonic_trend_is_strong() -> None:
    out = adx(_trend_candles(30), 14)
    assert out[27] is not None
    assert out[27] > 20.0


def test_adx_flat_series_is_zero() -> None:
    flat = [_c(100, 100, 100, 100) for _ in range(30)]
    out = adx(flat, 14)
    assert out[27] == pytest.approx(0.0)


def test_adx_future_mutation_does_not_change_history() -> None:
    candles = _trend_candles(40)
    baseline = adx(candles, 14)
    poisoned = list(candles)
    poisoned[31] = _c(1_000_000, 1_000_000, 1_000_000, 1_000_000)
    changed = adx(poisoned, 14)
    assert changed[:31] == baseline[:31]


def test_adx_is_deterministic() -> None:
    candles = _trend_candles(40)
    assert adx(candles, 14) == adx(candles, 14)


def test_adx_invalid_period_raises() -> None:
    with pytest.raises(ValueError):
        adx(_trend_candles(30), 0)


def test_bollinger_first_ready_index_is_19() -> None:
    out = bollinger([float(i) for i in range(30)], 20, 2.0)
    assert out[18] is None
    assert out[19] is not None


def test_bollinger_indices_before_first_are_none() -> None:
    out = bollinger([float(i) for i in range(30)], 20, 2.0)
    assert out[:19] == [None] * 19


def test_bollinger_uses_population_stddev_ddof_0() -> None:
    out = bollinger([1.0, 2.0, 3.0, 4.0], 4, 2.0)
    band = out[3]
    assert band is not None
    population_std = math.sqrt(1.25)  # ddof=0; sample std would be sqrt(5/3)
    assert band.middle == pytest.approx(2.5)
    assert band.upper == pytest.approx(2.5 + 2.0 * population_std)
    assert band.lower == pytest.approx(2.5 - 2.0 * population_std)


def test_bollinger_exact_values_on_hand_fixture() -> None:
    out = bollinger([10.0, 11.0, 9.0, 10.0], 4, 1.0)
    band = out[3]
    assert band is not None
    assert band.middle == pytest.approx(10.0)
    assert band.upper == pytest.approx(10.0 + math.sqrt(0.5))
    assert band.lower == pytest.approx(10.0 - math.sqrt(0.5))


def test_bollinger_flat_values_have_equal_bands() -> None:
    band = bollinger([10.0] * 25, 20, 2.0)[19]
    assert band is not None
    assert band.middle == pytest.approx(10.0)
    assert band.upper == pytest.approx(10.0)
    assert band.lower == pytest.approx(10.0)


def test_bollinger_causal_prefix_equality() -> None:
    series = [10.0 + (i % 7) * 0.1 for i in range(30)]
    full = bollinger(series, 20, 2.0)
    prefix = bollinger(series[:25], 20, 2.0)
    assert full[:25] == prefix[:25]


def test_bollinger_future_mutation_does_not_change_history() -> None:
    series = [10.0 + (i % 7) * 0.1 for i in range(30)]
    baseline = bollinger(series, 20, 2.0)
    poisoned = list(series)
    poisoned[26] = 1_000_000.0
    changed = bollinger(poisoned, 20, 2.0)
    assert changed[:26] == baseline[:26]


def test_bollinger_is_deterministic() -> None:
    series = [10.0 + (i % 5) * 0.2 for i in range(30)]
    assert bollinger(series, 20, 2.0) == bollinger(series, 20, 2.0)


@pytest.mark.parametrize("period", (0, -1))
def test_bollinger_invalid_period_raises(period: int) -> None:
    with pytest.raises(ValueError):
        bollinger([1.0] * 30, period, 2.0)


@pytest.mark.parametrize("multiplier", (0.0, -1.0, math.inf, math.nan))
def test_bollinger_invalid_multiplier_raises(multiplier: float) -> None:
    with pytest.raises(ValueError):
        bollinger([1.0] * 30, 20, multiplier)

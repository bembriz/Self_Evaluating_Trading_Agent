from application.services.validation import validate_candles
from domain.market.candle import Candle, Timeframe

MS = 60_000


def mk(ts: int) -> Candle:
    return Candle(ts, 100.0, 110.0, 90.0, 105.0, 1.0, 100.0)


def test_valid_continuous() -> None:
    r = validate_candles([mk(0), mk(15 * MS), mk(30 * MS)], Timeframe.M15)
    assert r.errors == ()
    assert r.warnings == ()


def test_duplicate_is_error() -> None:
    r = validate_candles([mk(0), mk(0), mk(15 * MS)], Timeframe.M15)
    assert any("duplicado" in e for e in r.errors)


def test_out_of_order_is_error() -> None:
    r = validate_candles([mk(15 * MS), mk(0)], Timeframe.M15)
    assert any("orden" in e for e in r.errors)


def test_misaligned_is_error() -> None:
    r = validate_candles([mk(1), mk(15 * MS)], Timeframe.M15)
    assert any("aline" in e for e in r.errors)


def test_gap_is_warning() -> None:
    r = validate_candles([mk(0), mk(45 * MS)], Timeframe.M15)
    assert r.errors == ()
    assert any("hueco" in w for w in r.warnings)


def test_empty_is_valid() -> None:
    r = validate_candles([], Timeframe.M15)
    assert r.errors == () and r.warnings == ()

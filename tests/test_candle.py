from datetime import UTC, datetime

import pytest

from domain.market.candle import Candle, Timeframe


def test_timeframe_minutes_and_label() -> None:
    assert Timeframe.M15.minutes == 15
    assert Timeframe.M15.label == "15m"
    assert Timeframe.H1.minutes == 60
    assert Timeframe.H1.label == "1h"
    assert Timeframe.H4.minutes == 240
    assert Timeframe.H4.label == "4h"


def test_timeframe_from_label_roundtrip() -> None:
    assert Timeframe.from_label("15m") is Timeframe.M15
    assert Timeframe.from_label("1h") is Timeframe.H1
    assert Timeframe.from_label("4h") is Timeframe.H4


def test_timeframe_from_label_unknown_raises() -> None:
    with pytest.raises(ValueError):
        Timeframe.from_label("5m")


def test_candle_timestamp_utc() -> None:
    c = Candle(1_700_000_000_000, 100.0, 110.0, 90.0, 105.0, 1.0, 100.0)
    assert c.timestamp == datetime.fromtimestamp(1_700_000_000, tz=UTC)


@pytest.mark.parametrize(
    "fields",
    [
        (100.0, 90.0, 90.0, 100.0, 1.0, 100.0),
        (100.0, 110.0, 110.0, 100.0, 1.0, 100.0),
        (100.0, 110.0, 90.0, 100.0, -1.0, 100.0),
        (100.0, 110.0, 90.0, 100.0, 1.0, -1.0),
    ],
)
def test_candle_invariants_raise(fields: tuple[float, ...]) -> None:
    o, h, lo, c, v, t = fields
    with pytest.raises(ValueError):
        Candle(1_700_000_000_000, o, h, lo, c, v, t)

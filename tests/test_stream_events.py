from domain.market.candle import Candle, Timeframe
from domain.market.stream import KlineUpdate


def test_kline_confirmed_to_candle() -> None:
    k = KlineUpdate("ETHUSDT", Timeframe.M15, 1000, 1.0, 2.0, 0.5, 1.5, 10.0, 20.0, confirm=True)
    assert k.to_candle() == Candle(1000, 1.0, 2.0, 0.5, 1.5, 10.0, 20.0)


def test_kline_unconfirmed_is_none() -> None:
    k = KlineUpdate("ETHUSDT", Timeframe.M15, 1000, 1.0, 2.0, 0.5, 1.5, 10.0, 20.0, confirm=False)
    assert k.to_candle() is None

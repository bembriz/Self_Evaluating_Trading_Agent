import pytest

from domain.evaluation.buy_hold import run_buy_and_hold
from domain.market.candle import Candle


def _c(ts: int, o: float, c: float) -> Candle:
    return Candle(ts, o, max(o, c), min(o, c), c, 1.0, c)


def _series(closes: list[float]) -> list[Candle]:
    out: list[Candle] = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else c
        out.append(_c(i * 3600_000, o, c))
    return out


def test_buy_and_hold_rising_is_profitable() -> None:
    m = run_buy_and_hold(_series([float(100 + i) for i in range(100)]))
    assert m.trades == 1
    assert m.net_pnl > 0
    assert m.gross_pnl > 0
    assert m.exposure == pytest.approx(1.0)


def test_buy_and_hold_falling_is_losing() -> None:
    m = run_buy_and_hold(_series([float(200 - i) for i in range(100)]))
    assert m.trades == 1
    assert m.net_pnl < 0


def test_buy_and_hold_empty() -> None:
    m = run_buy_and_hold([])
    assert m.trades == 0
    assert m.net_pnl == 0.0


def test_buy_and_hold_costs_are_nonzero() -> None:
    m = run_buy_and_hold(_series([100.0] * 50))
    assert m.fees > 0
    assert m.slippage > 0
    # Flat price: only costs remain, net < 0.
    assert m.net_pnl < 0

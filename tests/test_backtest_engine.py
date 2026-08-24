import pytest

from application.services.backtest_engine import BacktestEngine
from domain.market.candle import Candle
from domain.trading.signal import Action, Signal
from domain.trading.strategy import Strategy


class _Scripted(Strategy):
    version = "scripted"

    def __init__(self, actions: list[Action]) -> None:
        self._actions = actions
        self._i = 0

    def on_candle(self, candle: Candle) -> Signal:
        action = self._actions[min(self._i, len(self._actions) - 1)]
        self._i += 1
        return Signal(candle.timestamp_ms, action)


def _c(ts: int, o: float, c: float) -> Candle:
    return Candle(ts, o, max(o, c), min(o, c), c, 1.0, c)


def _rising(n: int, start: float = 100.0) -> list[Candle]:
    return [_c(i * 3600_000, start + i, start + i + 1) for i in range(n)]


def test_buy_then_sell_produces_profitable_trade() -> None:
    strategy = _Scripted([Action.HOLD, Action.BUY, Action.HOLD, Action.SELL, Action.HOLD])
    engine = BacktestEngine(strategy)
    result = engine.run(_rising(5))
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.quantity > 0
    assert trade.net_pnl > 0
    assert result.portfolio.position == 0.0


def test_deterministic_two_runs_identical() -> None:
    candles = _rising(200)
    actions = (
        [Action.HOLD] * 50
        + [Action.BUY] * 1
        + [Action.HOLD] * 50
        + [Action.SELL] * 1
        + [Action.HOLD] * 98
    )
    r1 = BacktestEngine(_Scripted(actions)).run(candles)
    r2 = BacktestEngine(_Scripted(actions)).run(candles)
    assert r1.equity_curve == r2.equity_curve
    assert r1.trades == r2.trades
    assert r1.metrics == r2.metrics


def test_trailing_signal_not_executed() -> None:
    strategy = _Scripted([Action.HOLD, Action.BUY, Action.SELL])
    engine = BacktestEngine(strategy)
    result = engine.run(_rising(3))
    # BUY en la vela 1 se ejecuta al open de la 2; SELL de la vela 2 (última) no se ejecuta.
    assert len(result.trades) == 0
    assert result.portfolio.position > 0


def test_hold_signals_do_nothing() -> None:
    strategy = _Scripted([Action.HOLD, Action.HOLD, Action.HOLD])
    engine = BacktestEngine(strategy)
    result = engine.run(_rising(3))
    assert result.trades == ()
    assert result.portfolio.position == 0.0
    assert result.portfolio.cash == pytest.approx(1000.0)


def test_buy_executes_at_next_open() -> None:
    # La señal de la vela 0 se ejecuta al open de la vela 1 (precio 101), no al close de la 0.
    candles = [_c(0, 100.0, 100.0), _c(3600_000, 101.0, 101.0), _c(7200_000, 101.0, 101.0)]
    strategy = _Scripted([Action.BUY, Action.HOLD, Action.HOLD])
    result = BacktestEngine(strategy).run(candles)
    assert len(result.trades) == 0
    assert result.portfolio.avg_entry == pytest.approx(101.0 * 1.0002)


def test_signals_count() -> None:
    strategy = _Scripted([Action.BUY, Action.SELL, Action.HOLD])
    result = BacktestEngine(strategy).run(_rising(3))
    assert result.signals == 2


def test_exposure_tracks_open_position() -> None:
    strategy = _Scripted([Action.BUY, Action.HOLD, Action.SELL])
    result = BacktestEngine(strategy).run(_rising(3))
    # BUY se ejecuta al open de la vela 1; posición abierta las velas 1 y 2.
    assert result.metrics.exposure == pytest.approx(2 / 3)

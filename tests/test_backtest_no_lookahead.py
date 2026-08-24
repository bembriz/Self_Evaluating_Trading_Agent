"""Tests anti-lookahead del motor de backtest (PRD §34).

El motor decide con la vela `i` y ejecuta al open de la vela `i+1`; envenenar velas
futuras no debe alterar la equity ni los trades cerrados antes del punto de envenenado.
"""

from __future__ import annotations

from application.services.backtest_engine import BacktestEngine
from domain.market.candle import Candle
from domain.trading.signal import Action, Signal
from domain.trading.strategy import EmaRsiBaseline, Strategy


class _Scripted(Strategy):
    version = "scripted"

    def __init__(self, actions: list[Action]) -> None:
        self._actions = actions
        self._i = 0

    def on_candle(self, candle: Candle) -> Signal:
        action = self._actions[min(self._i, len(self._actions) - 1)]
        self._i += 1
        return Signal(candle.timestamp_ms, action)


def _series(n: int) -> list[Candle]:
    out: list[Candle] = []
    prev = 100.0
    for i in range(n):
        close = prev * 1.001
        out.append(Candle(i * 3600_000, prev, close, prev, close, 1.0, close))
        prev = close
    return out


def _poisoned_candle(i: int) -> Candle:
    return Candle(i * 3600_000, 10**9, 10**9, 10**9, 10**9, 0.0, 0.0)


def test_engine_no_lookahead_equity_prefix() -> None:
    candles = _series(150)
    actions = (
        [Action.HOLD] * 40 + [Action.BUY] + [Action.HOLD] * 40 + [Action.SELL] + [Action.HOLD] * 68
    )
    base = BacktestEngine(_Scripted(actions)).run(candles)
    poisoned = candles[:100] + [_poisoned_candle(i) for i in range(100, 150)]
    poisoned_result = BacktestEngine(_Scripted(actions)).run(poisoned)
    assert poisoned_result.equity_curve[:100] == base.equity_curve[:100]
    cutoff = candles[100].timestamp_ms
    base_closed = [t for t in base.trades if t.exit_ts < cutoff]
    poisoned_closed = [t for t in poisoned_result.trades if t.exit_ts < cutoff]
    assert poisoned_closed == base_closed


def test_engine_replay_truncated_prefix() -> None:
    candles = _series(150)
    full = BacktestEngine(EmaRsiBaseline()).run(candles)
    truncated = BacktestEngine(EmaRsiBaseline()).run(candles[:120])
    assert truncated.equity_curve == full.equity_curve[:120]
    assert truncated.signals == full.signals or truncated.signals <= full.signals


def test_execution_uses_next_open_not_current_close() -> None:
    # Señal BUY en la vela 0 se ejecuta al open de la vela 1 (101), no al close de la 0 (100).
    candles = [
        Candle(0, 100.0, 100.0, 100.0, 100.0, 1.0, 100.0),
        Candle(3600_000, 101.0, 101.0, 101.0, 101.0, 1.0, 101.0),
        Candle(7200_000, 101.0, 101.0, 101.0, 101.0, 1.0, 101.0),
    ]
    result = BacktestEngine(_Scripted([Action.BUY, Action.HOLD, Action.HOLD])).run(candles)
    assert result.portfolio.avg_entry == 101.0 * 1.0002

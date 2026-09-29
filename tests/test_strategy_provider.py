"""Unit tests del StrategyDecisionProvider (adaptador estrategia → replay M7, M9-B).

Cubre: mapeo HOLD/BUY/SELL, signal_ts = close_time (open_time solo aserción),
secuencia estricta FAIL CLOSED, y paridad de señales de las tres estrategias
congeladas (EmaRsiBaseline, EthDonchianBreakout, EthBollingerMeanReversion)
contra su ejecución directa `on_candle`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

import pytest

from domain.market.candle import Candle
from domain.trading.signal import Action, Signal
from domain.trading.strategy import EmaRsiBaseline
from infrastructure.medallion.replay import CandleRow, ContextSnapshot, Decision, ReplayError
from infrastructure.medallion.strategy_provider import (
    StrategyDecisionProvider,
    rows_to_domain_candles,
)
from lab.strategies.eth_bollinger_mean_reversion import EthBollingerMeanReversion
from lab.strategies.eth_donchian_breakout import EthDonchianBreakout

DUR = 900_000


# ------------------------------------------------------------------ helpers


def _rows(n: int, *, start_ms: int = 0, close: float = 101.0) -> list[CandleRow]:
    out: list[CandleRow] = []
    for i in range(n):
        open_ms = start_ms + i * DUR
        out.append(
            CandleRow(
                open_time=open_ms,
                close_time=open_ms + DUR,
                open=close,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1.0,
                trade_count=1,
            )
        )
    return out


class _ScriptedStrategy:
    """Estrategia stub: acciones fijas por índice de llamada."""

    version = "stub-v1"

    def __init__(self, actions: dict[int, str], *, ts_offset_ms: int = 0) -> None:
        self._actions = actions
        self._offset = ts_offset_ms
        self._i = 0

    def on_candle(self, candle: Candle) -> Signal:
        action = self._actions.get(self._i, "hold")
        self._i += 1
        timestamp_ms = candle.timestamp_ms + (self._offset if action != "hold" else 0)
        return Signal(
            timestamp_ms=timestamp_ms,
            action=cast(Action, action),
        )


def _decide(
    provider: StrategyDecisionProvider,
    rows: Sequence[CandleRow],
    index: int,
    *,
    decision_ts: int | None = None,
    atr: float | None = 2.0,
    context: ContextSnapshot | None = None,
) -> Decision | None:
    row = rows[index]
    ts = row.close_time if decision_ts is None else decision_ts
    ctx = context if context is not None else ContextSnapshot(decision_ts=ts, h1=None, h4=None)
    return provider.decide(
        candle_index=index,
        decision_ts=ts,
        reference_price=row.close,
        atr_value=atr,
        context=ctx,
    )


def _provider(strategy: Any, rows: Sequence[CandleRow]) -> StrategyDecisionProvider:
    return StrategyDecisionProvider(strategy=strategy, candle_rows=rows)


def _direct_actions(strategy: object, candles: Sequence[Candle]) -> list[str | None]:
    out: list[str | None] = []
    for candle in candles:
        signal = strategy.on_candle(candle)  # type: ignore[attr-defined]
        if signal.action is Action.HOLD:
            out.append(None)
        else:
            out.append(signal.action.value)
    return out


def _provider_actions(
    provider: StrategyDecisionProvider, rows: Sequence[CandleRow]
) -> list[str | None]:
    out: list[str | None] = []
    for index in range(len(rows)):
        decision = _decide(provider, rows, index)
        out.append(None if decision is None else decision.action)
    return out


# ------------------------------------------------------- mapeo de decisiones


def test_hold_returns_none() -> None:
    rows = _rows(5)
    provider = _provider(_ScriptedStrategy({0: "hold"}), rows)
    assert _decide(provider, rows, 0) is None


def test_buy_maps_to_decision_buy() -> None:
    rows = _rows(5)
    provider = _provider(_ScriptedStrategy({0: "hold", 1: "hold", 2: "buy"}), rows)
    assert _decide(provider, rows, 0) is None
    assert _decide(provider, rows, 1) is None
    decision = _decide(provider, rows, 2, atr=3.5)
    assert decision is not None
    assert decision.action == "buy"
    assert decision.reference_price == rows[2].close
    assert decision.candle_index == 2
    assert decision.atr == 3.5


def test_sell_maps_to_decision_sell() -> None:
    rows = _rows(5)
    provider = _provider(_ScriptedStrategy({0: "hold", 1: "sell"}), rows)
    assert _decide(provider, rows, 0) is None
    decision = _decide(provider, rows, 1, atr=None)
    assert decision is not None
    assert decision.action == "sell"
    assert decision.atr is None


def test_signal_ts_is_close_time_never_open_time() -> None:
    rows = _rows(3)
    provider = _provider(_ScriptedStrategy({0: "buy"}), rows)
    decision = _decide(provider, rows, 0)
    assert decision is not None
    assert decision.signal_ts == rows[0].close_time
    assert decision.signal_ts != rows[0].open_time
    assert decision.signal_ts - rows[0].open_time == DUR


# ----------------------------------------------------------- FAIL CLOSED


def test_wrong_decision_ts_fails_closed() -> None:
    rows = _rows(3)
    provider = _provider(_ScriptedStrategy({0: "buy"}), rows)
    with pytest.raises(ReplayError):
        _decide(provider, rows, 0, decision_ts=rows[0].open_time)


def test_out_of_order_candle_index_fails_closed() -> None:
    rows = _rows(5)
    provider = _provider(_ScriptedStrategy({}), rows)
    with pytest.raises(ReplayError):
        _decide(provider, rows, 2)  # primer índice debe ser 0
    assert _decide(provider, rows, 0) is None
    with pytest.raises(ReplayError):
        _decide(provider, rows, 0)  # repetido


def test_signal_with_wrong_timestamp_fails_closed() -> None:
    rows = _rows(3)
    strategy = _ScriptedStrategy({1: "buy"}, ts_offset_ms=1)
    provider = _provider(strategy, rows)
    _decide(provider, rows, 0)
    with pytest.raises(ReplayError):
        _decide(provider, rows, 1)


def test_unknown_action_fails_closed() -> None:
    rows = _rows(3)
    provider = _provider(_ScriptedStrategy({0: "bogus"}), rows)
    with pytest.raises(ReplayError):
        _decide(provider, rows, 0)


def test_index_beyond_rows_fails_closed() -> None:
    rows = _rows(3)
    provider = _provider(_ScriptedStrategy({}), rows)
    with pytest.raises(ReplayError):
        provider.decide(
            candle_index=3,
            decision_ts=rows[-1].close_time,
            reference_price=rows[-1].close,
            atr_value=2.0,
            context=ContextSnapshot(decision_ts=rows[-1].close_time, h1=None, h4=None),
        )


def test_context_is_ignored_and_never_changes_the_decision() -> None:
    rows = _rows(4)
    provider = _provider(_ScriptedStrategy({0: "hold", 1: "buy"}), rows)
    assert _decide(provider, rows, 0) is None
    poisoned = ContextSnapshot(
        decision_ts=rows[1].close_time,
        h1=None,
        h4=None,
    )
    first = _decide(provider, rows, 1, context=ContextSnapshot(decision_ts=0, h1=None, h4=None))
    assert first is not None
    provider2 = _provider(_ScriptedStrategy({0: "hold", 1: "buy"}), rows)
    assert _decide(provider2, rows, 0) is None
    second = _decide(provider2, rows, 1, context=poisoned)
    assert second is not None
    assert first.action == second.action
    assert first.signal_ts == second.signal_ts


# --------------------------------------------------- paridad con estrategias


def _baseline_candles() -> list[CandleRow]:
    closes: list[float] = [100.0] * 60
    closes += [100.0 + 2.0 * (i - 59) for i in range(60, 75)]
    closes += [130.0] * 10
    closes += [130.0 - 3.0 * (i - 84) for i in range(85, 100)]
    closes += [85.0] * 40
    return [
        CandleRow(
            open_time=i * DUR,
            close_time=i * DUR + DUR,
            open=c,
            high=c + 0.5,
            low=c - 0.5,
            close=c,
            volume=1.0,
            trade_count=1,
        )
        for i, c in enumerate(closes)
    ]


def _donchian_candles() -> list[CandleRow]:
    closes: list[float] = [100.0] * 40
    closes += [101.0 + 1.0 * (i - 40) for i in range(40, 90)]
    closes += [150.0 - 2.0 * (i - 89) for i in range(90, 120)]
    return [
        CandleRow(
            open_time=i * DUR,
            close_time=i * DUR + DUR,
            open=c,
            high=c + 0.5,
            low=c - 0.5,
            close=c,
            volume=1.0,
            trade_count=1,
        )
        for i, c in enumerate(closes)
    ]


def _bollinger_candles() -> list[CandleRow]:
    closes: list[float] = []
    for i in range(120):
        closes.append(100.0 + (2.0 if i % 2 else -2.0))
    closes[39] = 90.0
    closes[40] = 99.0
    return [
        CandleRow(
            open_time=i * DUR,
            close_time=i * DUR + DUR,
            open=c,
            high=c,
            low=c,
            close=c,
            volume=1.0,
            trade_count=1,
        )
        for i, c in enumerate(closes)
    ]


def test_baseline_adapter_signal_parity() -> None:
    rows = _baseline_candles()
    candles = rows_to_domain_candles(rows)
    direct = _direct_actions(EmaRsiBaseline(), candles)
    via_provider = _provider_actions(_provider(EmaRsiBaseline(), rows), rows)
    assert direct == via_provider
    assert direct.count("buy") >= 1
    assert direct.count("sell") >= 1


def test_donchian_adapter_signal_parity() -> None:
    rows = _donchian_candles()
    candles = rows_to_domain_candles(rows)
    direct = _direct_actions(EthDonchianBreakout(candles=candles), candles)
    via_provider = _provider_actions(_provider(EthDonchianBreakout(candles=candles), rows), rows)
    assert direct == via_provider
    assert direct.count("buy") >= 1
    assert direct.count("sell") >= 1


def test_bollinger_adapter_signal_parity() -> None:
    rows = _bollinger_candles()
    candles = rows_to_domain_candles(rows)
    direct = _direct_actions(EthBollingerMeanReversion(candles=candles), candles)
    via_provider = _provider_actions(
        _provider(EthBollingerMeanReversion(candles=candles), rows), rows
    )
    assert direct == via_provider
    assert direct.count("buy") >= 1
    assert direct.count("sell") >= 1


def test_rows_to_domain_candles_uses_open_time_and_matches_rows_order() -> None:
    rows = _rows(4, start_ms=1_000_000)
    candles = rows_to_domain_candles(rows)
    assert len(candles) == len(rows)
    for row, candle in zip(rows, candles, strict=True):
        assert candle.timestamp_ms == row.open_time
        assert candle.open == row.open
        assert candle.close == row.close
        assert candle.volume == row.volume
        assert candle.turnover == 0.0

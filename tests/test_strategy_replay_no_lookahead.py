"""No-lookahead del adaptador estrategia → replay (M9-B).

Propiedad prefix: corromper velas FUTURAS (índice > k) no puede cambiar ninguna
decisión en índices <= k, para las tres estrategias congeladas (incremental y
preloaded), y el contexto 1h/4h jamás influye en la decisión.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import pytest

from domain.market.candle import Candle
from domain.trading.signal import Action
from domain.trading.strategy import EmaRsiBaseline
from infrastructure.medallion.replay import CandleRow, ContextSnapshot
from infrastructure.medallion.strategy_provider import (
    StrategyDecisionProvider,
    rows_to_domain_candles,
)
from lab.strategies.eth_bollinger_mean_reversion import EthBollingerMeanReversion
from lab.strategies.eth_donchian_breakout import EthDonchianBreakout

DUR = 900_000


# ------------------------------------------------------------------ helpers


def _row(close: float, index: int, *, high_off: float, low_off: float) -> CandleRow:
    return CandleRow(
        open_time=index * DUR,
        close_time=index * DUR + DUR,
        open=close,
        high=close + high_off,
        low=close - low_off,
        close=close,
        volume=1.0,
        trade_count=1,
    )


def _baseline_rows() -> list[CandleRow]:
    closes: list[float] = [100.0] * 60
    closes += [100.0 + 2.0 * (i - 59) for i in range(60, 75)]
    closes += [130.0] * 10
    closes += [130.0 - 3.0 * (i - 84) for i in range(85, 100)]
    closes += [85.0] * 40
    return [_row(c, i, high_off=0.5, low_off=0.5) for i, c in enumerate(closes)]


def _donchian_rows() -> list[CandleRow]:
    closes: list[float] = [100.0] * 40
    closes += [101.0 + 1.0 * (i - 40) for i in range(40, 90)]
    closes += [150.0 - 2.0 * (i - 89) for i in range(90, 120)]
    return [_row(c, i, high_off=0.5, low_off=0.5) for i, c in enumerate(closes)]


def _bollinger_rows() -> list[CandleRow]:
    closes: list[float] = []
    for i in range(120):
        closes.append(100.0 + (2.0 if i % 2 else -2.0))
    closes[39] = 90.0
    closes[40] = 99.0
    return [_row(c, i, high_off=0.0, low_off=0.0) for i, c in enumerate(closes)]


StrategyFactory = Callable[[Sequence[Candle]], object]

_STRATEGIES: dict[str, tuple[Callable[[], list[CandleRow]], StrategyFactory]] = {
    "baseline": (_baseline_rows, lambda candles: EmaRsiBaseline()),
    "donchian": (_donchian_rows, lambda candles: EthDonchianBreakout(candles=candles)),
    "bollinger": (_bollinger_rows, lambda candles: EthBollingerMeanReversion(candles=candles)),
}


def _decisions(
    factory: StrategyFactory, rows: Sequence[CandleRow]
) -> list[tuple[str | None, int | None]]:
    candles = rows_to_domain_candles(rows)
    provider = StrategyDecisionProvider(strategy=factory(candles), candle_rows=rows)  # type: ignore[arg-type]
    out: list[tuple[str | None, int | None]] = []
    for index in range(len(rows)):
        row = rows[index]
        decision = provider.decide(
            candle_index=index,
            decision_ts=row.close_time,
            reference_price=row.close,
            atr_value=2.0,
            context=ContextSnapshot(decision_ts=row.close_time, h1=None, h4=None),
        )
        out.append((None, None) if decision is None else (decision.action, decision.signal_ts))
    return out


def _corrupt_future(rows: list[CandleRow], start: int) -> list[CandleRow]:
    out: list[CandleRow] = []
    for i, row in enumerate(rows):
        if i >= start:
            out.append(
                CandleRow(
                    open_time=row.open_time,
                    close_time=row.close_time,
                    open=row.open + 7.0,
                    high=row.high + 7.0,
                    low=row.low + 7.0,
                    close=row.close + 7.0,
                    volume=row.volume,
                    trade_count=row.trade_count,
                )
            )
        else:
            out.append(row)
    return out


@pytest.mark.parametrize("name", sorted(_STRATEGIES))
def test_future_candle_corruption_never_changes_past_decisions(name: str) -> None:
    build_rows, factory = _STRATEGIES[name]
    rows = build_rows()
    base = _decisions(factory, rows)
    first_signal = next((i for i, (action, _) in enumerate(base) if action is not None), None)
    assert first_signal is not None, f"{name}: sin señales — fixture no válida"
    k = min(first_signal + 2, len(rows) - 2)
    corrupted = _decisions(factory, _corrupt_future(rows, k + 1))
    assert corrupted[: k + 1] == base[: k + 1]
    assert any(action is not None for action, _ in base[: k + 1])


def test_decisions_equal_on_identical_runs() -> None:
    for name in sorted(_STRATEGIES):
        build_rows, factory = _STRATEGIES[name]
        rows = build_rows()
        assert _decisions(factory, rows) == _decisions(factory, rows), name


def test_action_values_are_valid_catalog() -> None:
    for name in sorted(_STRATEGIES):
        build_rows, factory = _STRATEGIES[name]
        rows = build_rows()
        for action, _ts in _decisions(factory, rows):
            assert action in {None, Action.BUY.value, Action.SELL.value}, (name, action)

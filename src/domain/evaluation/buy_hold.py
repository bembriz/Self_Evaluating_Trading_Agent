"""Benchmark Buy & Hold (PRD §31). Dominio puro.

Compra con todo el cash al open de la primera vela, mantiene y vende al close de la
última. Reutiliza `FillModel`/`Portfolio`/`compute_metrics` para que las métricas sean
directamente comparables con el baseline.
"""

from __future__ import annotations

from collections.abc import Sequence

from domain.evaluation.metrics import PerformanceMetrics, compute_metrics
from domain.market.candle import Candle
from domain.portfolio.portfolio import Portfolio
from domain.trading.fill import FillModel


def run_buy_and_hold(
    candles: Sequence[Candle],
    fill_model: FillModel | None = None,
    initial_cash: float = 1000.0,
    periods_per_year: float = 8760.0,
) -> PerformanceMetrics:
    model = fill_model or FillModel()
    if not candles:
        return compute_metrics([], [], periods_per_year)
    portfolio = Portfolio(initial_cash=initial_cash, cash=initial_cash)
    first = candles[0]
    portfolio.apply_buy(model.buy(first.timestamp_ms, first.open, portfolio.cash))

    equity = [portfolio.equity(c.close) for c in candles]
    last = candles[-1]
    portfolio.apply_sell(model.sell(last.timestamp_ms, last.close, portfolio.position))
    equity[-1] = portfolio.equity(last.close)

    n = len(candles)
    return compute_metrics(
        portfolio.trades,
        equity,
        periods_per_year=periods_per_year,
        exposure=1.0,
        avg_holding_bars=float(n - 1),
    )

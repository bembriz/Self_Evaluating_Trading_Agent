"""Motor de backtesting event-driven determinista (PRD §25, §29). Dominio puro.

Regla de no-lookahead (PRD §34): la señal generada al cierre de la vela `i` se ejecuta
al open de la vela `i+1`. La señal de la última vela nunca se ejecuta. La señal HOLD no
produce fill. Iteración estrictamente ordenada por `timestamp_ms`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from domain.evaluation.metrics import PerformanceMetrics, compute_metrics
from domain.market.candle import Candle
from domain.portfolio.portfolio import Portfolio, Trade
from domain.trading.fill import FillModel
from domain.trading.signal import Action, Signal
from domain.trading.strategy import Strategy


@dataclass(frozen=True, slots=True)
class BacktestResult:
    portfolio: Portfolio
    trades: tuple[Trade, ...]
    equity_curve: tuple[float, ...]
    metrics: PerformanceMetrics
    signals: int


class BacktestEngine:
    def __init__(
        self,
        strategy: Strategy,
        fill_model: FillModel | None = None,
        initial_cash: float = 1000.0,
        periods_per_year: float = 8760.0,
    ) -> None:
        self._strategy = strategy
        self._fill_model = fill_model or FillModel()
        self._initial_cash = initial_cash
        self._periods_per_year = periods_per_year

    def run(self, candles: Sequence[Candle]) -> BacktestResult:
        portfolio = Portfolio(initial_cash=self._initial_cash, cash=self._initial_cash)
        equity: list[float] = []
        pending: Signal | None = None
        signals = 0
        open_bars = 0
        holding_bars: list[int] = []
        entry_bar: int | None = None

        for i, candle in enumerate(candles):
            if pending is not None:
                before = portfolio.position
                self._execute(pending, candle.open, candle.timestamp_ms, portfolio)
                if pending.action is Action.BUY and before == 0.0 and portfolio.position > 0:
                    entry_bar = i
                if pending.action is Action.SELL and portfolio.position == 0.0 and before > 0:
                    holding_bars.append(i - (entry_bar if entry_bar is not None else i))
                    entry_bar = None
                pending = None

            signal = self._strategy.on_candle(candle)
            if signal.action is not Action.HOLD:
                signals += 1
            pending = signal

            equity.append(portfolio.equity(candle.close))
            if portfolio.position > 0:
                open_bars += 1

        exposure = open_bars / len(candles) if candles else 0.0
        avg_holding_bars = sum(holding_bars) / len(holding_bars) if holding_bars else 0.0
        metrics = compute_metrics(
            portfolio.trades,
            equity,
            periods_per_year=self._periods_per_year,
            exposure=exposure,
            avg_holding_bars=avg_holding_bars,
        )
        return BacktestResult(
            portfolio=portfolio,
            trades=tuple(portfolio.trades),
            equity_curve=tuple(equity),
            metrics=metrics,
            signals=signals,
        )

    def _execute(
        self, signal: Signal, price: float, timestamp_ms: int, portfolio: Portfolio
    ) -> None:
        if signal.action is Action.BUY:
            fill = self._fill_model.buy(timestamp_ms, price, portfolio.cash)
            portfolio.apply_buy(fill)
        elif signal.action is Action.SELL and portfolio.position > 0:
            fill = self._fill_model.sell(timestamp_ms, price, portfolio.position)
            portfolio.apply_sell(fill)

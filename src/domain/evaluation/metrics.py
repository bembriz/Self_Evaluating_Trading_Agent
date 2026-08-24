"""Métricas de trading (PRD §45). Dominio puro, determinista.

- `max_drawdown`, `win_rate`, `loss_rate`, `exposure` se expresan como fracción [0, 1].
- `sharpe`/`sortino` se anualizan con `sqrt(periods_per_year)` y devuelven `None` si no
  hay varianza/downside definibles.
- `profit_factor` devuelve `inf` si no hay pérdidas con ganancias, y `None` sin trades.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from domain.portfolio.portfolio import Trade


@dataclass(frozen=True, slots=True)
class PerformanceMetrics:
    gross_pnl: float
    net_pnl: float
    fully_loaded_pnl: float
    fees: float
    slippage: float
    llm_cost: float
    trades: int
    win_rate: float | None
    loss_rate: float | None
    profit_factor: float | None
    sharpe: float | None
    sortino: float | None
    max_drawdown: float
    expectancy: float | None
    avg_winner: float | None
    avg_loser: float | None
    risk_reward: float | None
    avg_holding_bars: float
    exposure: float


def compute_metrics(
    trades: Sequence[Trade],
    equity_curve: Sequence[float],
    periods_per_year: float,
    llm_cost: float = 0.0,
    exposure: float = 0.0,
    avg_holding_bars: float = 0.0,
) -> PerformanceMetrics:
    gross_pnl = sum(t.gross_pnl for t in trades)
    fees = sum(t.fees for t in trades)
    slippage = sum(t.slippage for t in trades)
    net_pnl = gross_pnl - fees - slippage
    fully_loaded_pnl = net_pnl - llm_cost

    winners = [t.net_pnl for t in trades if t.net_pnl > 0]
    losers = [t.net_pnl for t in trades if t.net_pnl < 0]

    win_rate = len(winners) / len(trades) if trades else None
    loss_rate = (1.0 - win_rate) if win_rate is not None else None

    gross_profit = sum(winners)
    gross_loss = -sum(losers)
    if not trades:
        profit_factor = None
    elif gross_loss == 0:
        profit_factor = float("inf") if gross_profit > 0 else None
    else:
        profit_factor = gross_profit / gross_loss

    rets = _returns(equity_curve)
    sharpe = _sharpe(rets, periods_per_year)
    sortino = _sortino(rets, periods_per_year)
    max_drawdown = _max_drawdown(equity_curve)

    expectancy = statistics.mean([t.net_pnl for t in trades]) if trades else None
    avg_winner = statistics.mean(winners) if winners else None
    avg_loser = statistics.mean(losers) if losers else None
    if avg_winner is not None and avg_loser is not None and avg_loser != 0:
        risk_reward = avg_winner / abs(avg_loser)
    else:
        risk_reward = None

    return PerformanceMetrics(
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        fully_loaded_pnl=fully_loaded_pnl,
        fees=fees,
        slippage=slippage,
        llm_cost=llm_cost,
        trades=len(trades),
        win_rate=win_rate,
        loss_rate=loss_rate,
        profit_factor=profit_factor,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_drawdown,
        expectancy=expectancy,
        avg_winner=avg_winner,
        avg_loser=avg_loser,
        risk_reward=risk_reward,
        avg_holding_bars=avg_holding_bars,
        exposure=exposure,
    )


def _returns(equity: Sequence[float]) -> list[float]:
    rets: list[float] = []
    for i in range(1, len(equity)):
        prev = equity[i - 1]
        if prev != 0:
            rets.append((equity[i] - prev) / prev)
    return rets


def _sharpe(rets: Sequence[float], periods_per_year: float) -> float | None:
    if len(rets) < 2:
        return None
    std = statistics.stdev(rets)
    if std == 0:
        return None
    return statistics.mean(rets) / std * math.sqrt(periods_per_year)


def _sortino(rets: Sequence[float], periods_per_year: float) -> float | None:
    if len(rets) < 2:
        return None
    downside = [r for r in rets if r < 0]
    if not downside:
        return None
    downside_dev = math.sqrt(sum(r * r for r in downside) / len(rets))
    return statistics.mean(rets) / downside_dev * math.sqrt(periods_per_year)


def _max_drawdown(equity: Sequence[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    max_dd = 0.0
    for eq in equity:
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak)
    return max_dd

"""Walk-forward MVP sobre WALK_FORWARD (Fase 17F).

Ventanas contiguas que cubren [62208, 88128) sin solapes ni huecos, cada una
ejecutada por separado con FrozenDatasetAdapter + LabSessionRunner (el
cableado vive en los callers; aquí solo geometría y métricas puras).

Métricas reutilizadas de `domain.evaluation.metrics` (sin duplicar fórmulas):
los round-trips se reconstruyen de la traza (long-only, una posición: cada
fill BUY se aparea con el siguiente fill SELL) y la curva de equity sale de
la traza + equity inicial. Cada ventana corre con motor fresco (mismo
capital), por lo que los retornos son aditivos en el agregado.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

from domain.evaluation.metrics import compute_metrics
from domain.portfolio.portfolio import Trade
from lab.session_runner import LabCandleEvent, LabSessionResult
from lab.splits import WALK_FORWARD_END, WALK_FORWARD_START

PERIODS_PER_YEAR_15M = 365 * 96
DEFAULT_WINDOW_COUNT = 3


@dataclass(frozen=True, slots=True)
class WindowSpec:
    """Ventana contigua [row_start, row_end) dentro de WALK_FORWARD."""

    index: int
    row_start: int
    row_end: int


def walk_forward_windows(n_windows: int = DEFAULT_WINDOW_COUNT) -> tuple[WindowSpec, ...]:
    """Divide WALK_FORWARD en n ventanas contiguas de cobertura total."""
    total = WALK_FORWARD_END - WALK_FORWARD_START
    if isinstance(n_windows, bool) or not isinstance(n_windows, int):
        raise ValueError("n_windows must be an integer")
    if n_windows < 1 or n_windows > total:
        raise ValueError(f"n_windows out of range: {n_windows}")
    base, extra = divmod(total, n_windows)
    specs: list[WindowSpec] = []
    start = WALK_FORWARD_START
    for index in range(n_windows):
        size = base + (1 if index < extra else 0)
        specs.append(WindowSpec(index=index, row_start=start, row_end=start + size))
        start += size
    # Cobertura total garantizada por construcción (encadenado desde
    # WALK_FORWARD_START consumiendo `total` filas); los tests la verifican.
    return tuple(specs)


def trades_from_trace(events: tuple[LabCandleEvent, ...]) -> tuple[Trade, ...]:
    """Reconstruye round-trips BUY→SELL de la traza (sin posición cruzada)."""
    trades: list[Trade] = []
    open_lot: LabCandleEvent | None = None
    for event in events:
        if event.filled and event.action == "BUY":
            open_lot = event
        elif event.filled and event.action == "SELL" and open_lot is not None:
            buy = open_lot
            open_lot = None
            quantity = min(buy.quantity or 0.0, event.quantity or 0.0)
            gross = ((event.exec_price or 0.0) - (buy.exec_price or 0.0)) * quantity
            fees = (buy.fee or 0.0) + (event.fee or 0.0)
            slippage = (buy.slippage_cost or 0.0) + (event.slippage_cost or 0.0)
            trades.append(
                Trade(
                    entry_ts=buy.timestamp_ms,
                    exit_ts=event.timestamp_ms,
                    entry_price=buy.exec_price or 0.0,
                    exit_price=event.exec_price or 0.0,
                    quantity=quantity,
                    gross_pnl=gross,
                    fees=fees,
                    slippage=slippage,
                    net_pnl=gross - fees - slippage,
                )
            )
    return tuple(trades)


def window_metrics(result: LabSessionResult) -> dict[str, Any]:
    """Métricas de una ventana desde su LabSessionResult (puro, determinista)."""
    initial = float(result.metrics.get("equity_initial", 0.0))
    equity_curve = [initial, *(event.equity for event in result.events)]
    trades = trades_from_trace(result.events)
    perf = compute_metrics(list(trades), equity_curve, PERIODS_PER_YEAR_15M)
    net = perf.net_pnl
    return {
        "trades": perf.trades,
        "net_pnl": net,
        "return_pct": net / initial if initial else 0.0,
        "max_drawdown": perf.max_drawdown,
        "profit_factor": perf.profit_factor,
        "expectancy": perf.expectancy,
    }


@dataclass(frozen=True)
class WindowResult:
    """Resultado de una ventana con referencias a su ExperimentRun."""

    index: int
    row_start: int
    row_end: int
    first_timestamp_ms: int
    last_timestamp_ms: int
    trades: int
    net_pnl: float
    return_pct: float
    max_drawdown: float
    profit_factor: float | None
    expectancy: float | None
    experiment_spec_id: str
    run_id: str
    event_trace_hash: str | None
    metrics_hash: str | None


def make_window_result(
    window: WindowSpec, result: LabSessionResult, *, run_id: str
) -> WindowResult:
    """Empaqueta ventana + resultado + referencias (puro, determinista)."""
    metrics = window_metrics(result)
    events = result.events
    return WindowResult(
        index=window.index,
        row_start=window.row_start,
        row_end=window.row_end,
        first_timestamp_ms=events[0].timestamp_ms,
        last_timestamp_ms=events[-1].timestamp_ms,
        trades=int(metrics["trades"]),
        net_pnl=float(metrics["net_pnl"]),
        return_pct=float(metrics["return_pct"]),
        max_drawdown=float(metrics["max_drawdown"]),
        profit_factor=metrics["profit_factor"],
        expectancy=metrics["expectancy"],
        experiment_spec_id=result.experiment_spec_id,
        run_id=run_id,
        event_trace_hash=result.event_trace_hash,
        metrics_hash=result.metrics_hash_value,
    )


def aggregate_results(results: tuple[WindowResult, ...]) -> dict[str, Any]:
    """Agregado walk-forward (puro, determinista; sin estadística avanzada)."""
    if not results:
        raise ValueError("no window results to aggregate")
    nets = [item.net_pnl for item in results]
    returns = [item.return_pct for item in results]
    total_trades = sum(item.trades for item in results)
    gross_profit = sum(net for net in nets if net > 0)
    gross_loss = -sum(net for net in nets if net < 0)
    if total_trades == 0:
        profit_factor = None
    elif gross_loss == 0:
        profit_factor = float("inf") if gross_profit > 0 else None
    else:
        profit_factor = gross_profit / gross_loss
    return {
        "total_windows": len(results),
        "profitable_windows": sum(1 for net in nets if net > 0),
        "losing_windows": sum(1 for net in nets if net < 0),
        "aggregate_net_pnl": sum(nets),
        "aggregate_return_pct": sum(returns),
        "median_window_return": statistics.median(returns),
        "worst_window_return": min(returns),
        "max_drawdown": max(item.max_drawdown for item in results),
        "total_trades": total_trades,
        "profit_factor": profit_factor,
        "expectancy": (sum(nets) / total_trades) if total_trades else None,
    }

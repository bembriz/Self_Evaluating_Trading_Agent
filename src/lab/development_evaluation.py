"""Fase 18B — evaluación económica DEVELOPMENT: baseline vs BTC-context.

Funciones puras y deterministas que reutilizan las métricas existentes
(`domain.evaluation.metrics.compute_metrics`) y la reconstrucción de trades de
`lab.walk_forward.trades_from_trace`; no definen fórmulas nuevas.

El criterio IMPROVED/MIXED/NOT_IMPROVED es predeclarado (fijado antes de ver
resultados) y no se ajusta a posteriori. No existe score compuesto.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from domain.evaluation.metrics import compute_metrics
from domain.trading.signal import Action, Signal
from lab.session_runner import LabSessionResult
from lab.walk_forward import PERIODS_PER_YEAR_15M, trades_from_trace

# Umbral material predeclarado de Max Drawdown (fracción absoluta del capital).
MAX_DRAWDOWN_MATERIAL_ABS = 0.01


def count_signals(signals: Sequence[Signal]) -> dict[str, int]:
    """Cuenta decisiones BUY/SELL/HOLD (unidad: señal de estrategia)."""
    buy = sell = hold = 0
    for signal in signals:
        if signal.action is Action.BUY:
            buy += 1
        elif signal.action is Action.SELL:
            sell += 1
        else:
            hold += 1
    return {"signals_buy": buy, "signals_sell": sell, "signals_hold": hold}


def session_metrics(result: LabSessionResult) -> dict[str, Any]:
    """Métricas económicas completas desde una LabSessionResult (fórmulas existentes)."""
    initial = float(result.metrics.get("equity_initial", 0.0))
    equity_curve = [initial, *(event.equity for event in result.events)]
    trades = list(trades_from_trace(result.events))
    perf = compute_metrics(trades, equity_curve, PERIODS_PER_YEAR_15M)
    return {
        "closed_trades": perf.trades,
        "fills": sum(1 for event in result.events if event.filled),
        "net_pnl": perf.net_pnl,
        "return_pct": perf.net_pnl / initial if initial else 0.0,
        "fees": perf.fees,
        "slippage": perf.slippage,
        "max_drawdown": perf.max_drawdown,
        "profit_factor": perf.profit_factor,
        "expectancy": perf.expectancy,
        "win_rate": perf.win_rate,
        "average_win": perf.avg_winner,
        "average_loss": perf.avg_loser,
    }


def _finite(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return value


def _delta(candidate: float | None, baseline: float | None) -> float | None:
    cand = _finite(candidate)
    base = _finite(baseline)
    if cand is None or base is None:
        return None
    return cand - base


def compare_metrics(baseline: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Deltas explícitos baseline→candidate y reducción de operaciones."""
    base_trades = int(baseline["closed_trades"])
    cand_trades = int(candidate["closed_trades"])
    trade_reduction = (base_trades - cand_trades) / base_trades * 100.0 if base_trades else 0.0
    return {
        "delta_net_pnl": float(candidate["net_pnl"]) - float(baseline["net_pnl"]),
        "delta_return_pct": float(candidate["return_pct"]) - float(baseline["return_pct"]),
        "delta_max_drawdown": float(candidate["max_drawdown"]) - float(baseline["max_drawdown"]),
        "delta_profit_factor": _delta(candidate["profit_factor"], baseline["profit_factor"]),
        "delta_expectancy": _delta(candidate["expectancy"], baseline["expectancy"]),
        "delta_trades": cand_trades - base_trades,
        "delta_fees": float(candidate["fees"]) - float(baseline["fees"]),
        "delta_slippage": float(candidate["slippage"]) - float(baseline["slippage"]),
        "trade_reduction_percent": trade_reduction,
    }


def btc_filter_attribution(
    baseline_signals: Sequence[Signal],
    candidate_signals: Sequence[Signal],
    baseline_result: LabSessionResult,
) -> dict[str, Any]:
    """Contabilidad del filtro BTC + análisis descriptivo de los BUY bloqueados.

    `baseline_buy_candidates = btc_confirmed_buys + btc_blocked_buys`. Los BUY
    bloqueados se cruzan con los round-trips reales del baseline por timestamp de
    entrada; no se altera ninguna decisión.
    """
    if len(baseline_signals) != len(candidate_signals):
        raise ValueError("baseline/candidate signal length mismatch")
    baseline_buys = 0
    candidate_buys = 0
    blocked_timestamps: list[int] = []
    for base_signal, cand_signal in zip(baseline_signals, candidate_signals, strict=True):
        if base_signal.action is Action.BUY:
            baseline_buys += 1
            if cand_signal.action is Action.HOLD:
                blocked_timestamps.append(base_signal.timestamp_ms)
        if cand_signal.action is Action.BUY:
            candidate_buys += 1
    if candidate_buys + len(blocked_timestamps) != baseline_buys:
        raise ValueError("BTC filter changed decisions outside BUY→HOLD")
    trades_by_entry = {trade.entry_ts: trade for trade in trades_from_trace(baseline_result.events)}
    blocked_trades = [
        trades_by_entry[timestamp]
        for timestamp in blocked_timestamps
        if timestamp in trades_by_entry
    ]
    net = [trade.net_pnl for trade in blocked_trades]
    winners = [value for value in net if value > 0.0]
    losers = [value for value in net if value < 0.0]
    flats = [value for value in net if value == 0.0]
    return {
        "baseline_buy_candidates": baseline_buys,
        "btc_confirmed_buys": candidate_buys,
        "btc_blocked_buys": len(blocked_timestamps),
        "blocked_baseline_trades": len(blocked_trades),
        "blocked_baseline_net_pnl": sum(net),
        "blocked_baseline_winners": len(winners),
        "blocked_baseline_losers": len(losers),
        "blocked_baseline_flats": len(flats),
        "blocked_baseline_avg_net_pnl": (sum(net) / len(net)) if net else None,
    }


def _better(candidate: float | None, baseline: float | None) -> bool:
    cand = _finite(candidate)
    base = _finite(baseline)
    return cand is not None and base is not None and cand > base


def _worse(candidate: float | None, baseline: float | None) -> bool:
    cand = _finite(candidate)
    base = _finite(baseline)
    return cand is not None and base is not None and cand < base


def classify_development_result(baseline: Mapping[str, Any], candidate: Mapping[str, Any]) -> str:
    """Criterio predeclarado IMPROVED/MIXED/NOT_IMPROVED (sin score compuesto)."""
    expectancy_better = _better(candidate["expectancy"], baseline["expectancy"])
    pf_better = _better(candidate["profit_factor"], baseline["profit_factor"])
    net_better = float(candidate["net_pnl"]) > float(baseline["net_pnl"])
    dd_material = float(candidate["max_drawdown"]) > (
        float(baseline["max_drawdown"]) + MAX_DRAWDOWN_MATERIAL_ABS
    )
    if expectancy_better and pf_better and net_better and not dd_material:
        return "IMPROVED"
    improvements = int(expectancy_better) + int(pf_better) + int(net_better)
    deteriorations = (
        int(_worse(candidate["expectancy"], baseline["expectancy"]))
        + int(_worse(candidate["profit_factor"], baseline["profit_factor"]))
        + int(float(candidate["net_pnl"]) < float(baseline["net_pnl"]))
    )
    if improvements == 0 or deteriorations >= 2:
        return "NOT_IMPROVED"
    return "MIXED"

"""Sensibilidades de costes/parámetros y análisis por regímenes (PRD §47).

Todas las métricas sobre PnL NETO. Una estrategia cuyo resultado dependa de un
punto extremadamente estrecho del espacio de parámetros se rechaza.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain.portfolio.portfolio import Trade


@dataclass(frozen=True, slots=True)
class SensitivityPoint:
    """Resultado neto bajo un nivel de coste adicional (en bps por lado)."""

    bps: float
    total_net_pnl: float
    extra_cost_usd: float
    survives: bool


def _notional(trade: Trade) -> float:
    return trade.quantity * (trade.entry_price + trade.exit_price)


def _cost_sensitivity(
    trades: list[Trade], bps_range: tuple[float, ...], *, kind: str
) -> list[SensitivityPoint]:
    baseline = sum(t.net_pnl for t in trades)
    points: list[SensitivityPoint] = []
    for bps in bps_range:
        extra = sum(_notional(t) * (bps / 10_000.0) for t in trades)
        net = baseline - extra
        points.append(
            SensitivityPoint(bps=bps, total_net_pnl=net, extra_cost_usd=extra, survives=net > 0.0)
        )
    return points


def fee_sensitivity(trades: list[Trade], *, bps_range: tuple[float, ...]) -> list[SensitivityPoint]:
    """PnL neto bajo tasas de fee crecientes (por lado)."""
    return _cost_sensitivity(trades, bps_range, kind="fee")


def slippage_sensitivity(
    trades: list[Trade], *, bps_range: tuple[float, ...]
) -> list[SensitivityPoint]:
    """PnL neto bajo slippage creciente (por lado)."""
    return _cost_sensitivity(trades, bps_range, kind="slippage")


# --------------------------------------------------------------- parámetros


@dataclass(frozen=True, slots=True)
class ParameterSensitivityReport:
    best_params: tuple[float, ...]
    best_net_pnl: float
    neighbor_profitable_ratio: float
    is_robust: bool


def parameter_sensitivity(
    grid_results: dict[tuple[Any, ...], float],
    *,
    min_neighbor_ratio: float = 0.5,
) -> ParameterSensitivityReport:
    """¿Vecindario rentable o pico estrecho? Vecinos = distancia 1 en cada eje."""
    if not grid_results:
        raise ValueError("grid vacío")
    best_key = max(grid_results, key=lambda k: grid_results[k])
    best_params: tuple[float, ...] = tuple(float(x) for x in best_key)
    best_pnl = grid_results[best_key]
    normalized = {tuple(float(x) for x in k): v for k, v in grid_results.items()}

    neighbors: list[float] = []
    dims = len(best_params)
    for axis in range(dims):
        for delta in (-1, 1):
            probe = list(best_params)
            probe[axis] += delta
            key = tuple(float(v) for v in probe)
            if key in normalized:
                neighbors.append(normalized[key])
    ratio = sum(1 for v in neighbors if v > 0.0) / len(neighbors) if neighbors else 0.0
    return ParameterSensitivityReport(
        best_params=best_params,
        best_net_pnl=best_pnl,
        neighbor_profitable_ratio=ratio,
        is_robust=best_pnl > 0.0 and ratio >= min_neighbor_ratio,
    )


# ------------------------------------------------------------------ regímenes


@dataclass(frozen=True, slots=True)
class RegimeStats:
    regime: str
    n_trades: int
    net_pnl: float
    win_rate: float
    profitable: bool


@dataclass(frozen=True, slots=True)
class RegimeReport:
    per_regime: list[RegimeStats]
    profitable_regimes: int
    meets_two_regime_rule: bool


def analyze_regimes(
    trades_by_regime: list[tuple[str, list[Trade]]],
) -> RegimeReport:
    """Regla §47: funcionar positivamente en al menos dos regímenes."""
    stats: list[RegimeStats] = []
    profitable = 0
    for regime, trades in trades_by_regime:
        if not trades:
            continue
        net = sum(t.net_pnl for t in trades)
        wins = sum(1 for t in trades if t.net_pnl > 0)
        is_profitable = net > 0.0
        profitable += int(is_profitable)
        stats.append(
            RegimeStats(
                regime=regime,
                n_trades=len(trades),
                net_pnl=net,
                win_rate=wins / len(trades),
                profitable=is_profitable,
            )
        )
    return RegimeReport(
        per_regime=stats,
        profitable_regimes=profitable,
        meets_two_regime_rule=profitable >= 2,
    )

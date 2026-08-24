"""Bootstrap y Monte Carlo sobre trades cerrados (PRD §47). Dominio puro.

Percentile bootstrap con seed registrado (B>=1000 recomendado) para ICs de
expectancy/Sharpe; Monte Carlo por permutación de la secuencia de PnL netos
para distribución de drawdowns y probabilidad de ruina.
"""

from __future__ import annotations

import random
import statistics
from collections.abc import Callable
from dataclasses import dataclass

_TRADING_DAYS = 252


@dataclass(frozen=True, slots=True)
class ConfidenceInterval:
    """IC por percentile bootstrap de una estadística muestral."""

    point: float
    low: float
    high: float
    n_samples: int
    n_bootstraps: int
    method: str = "percentile-bootstrap"


def _percentile(sorted_values: list[float], q: float) -> float:
    idx = min(int(q * (len(sorted_values) - 1) + 0.5), len(sorted_values) - 1)
    return sorted_values[idx]


def bootstrap_ci(
    values: list[float],
    *,
    statistic: Callable[[list[float]], float] = statistics.mean,
    n_bootstraps: int = 1000,
    seed: int = 42,
    ci_level: float = 0.95,
) -> ConfidenceInterval:
    """IC percentile bootstrap; determinista dado el seed."""
    if not values:
        raise ValueError("muestra vacía")
    rng = random.Random(seed)
    point = statistic(values)
    stats: list[float] = []
    n = len(values)
    for _ in range(n_bootstraps):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        stats.append(statistic(sample))
    stats.sort()
    alpha = (1.0 - ci_level) / 2.0
    return ConfidenceInterval(
        point=point,
        low=_percentile(stats, alpha),
        high=_percentile(stats, 1.0 - alpha),
        n_samples=n,
        n_bootstraps=n_bootstraps,
    )


def sharpe_of(returns: list[float], periods_per_year: float = _TRADING_DAYS) -> float | None:
    """Sharpe anualizado simple; None si no es calculable."""
    if len(returns) < 2:
        return None
    sd = statistics.stdev(returns)
    if sd == 0.0:
        return None
    return float(statistics.mean(returns) / sd * (periods_per_year**0.5))


@dataclass(frozen=True, slots=True)
class MonteCarloReport:
    """Distribución de drawdowns máximos y riesgo de ruina."""

    p50_drawdown: float
    p95_drawdown: float
    p99_drawdown: float
    ruin_probability: float
    n_sims: int


def monte_carlo_drawdown(
    *,
    net_pnls: list[float],
    initial_capital: float,
    n_sims: int,
    seed: int,
    ruin_threshold: float = 0.5,
) -> MonteCarloReport:
    """Permuta la secuencia de PnL netos y mide drawdown máximo por simulación."""
    if not net_pnls or initial_capital <= 0.0:
        raise ValueError("se requieren trades y capital positivo")
    rng = random.Random(seed)
    max_dds: list[float] = []
    ruined = 0
    for _ in range(n_sims):
        shuffled = list(net_pnls)
        rng.shuffle(shuffled)
        equity = initial_capital
        peak = equity
        max_dd = 0.0
        broke = False
        for pnl in shuffled:
            equity += pnl
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
            if equity <= initial_capital * (1.0 - ruin_threshold):
                broke = True
                break
        if broke:
            ruined += 1
        max_dds.append(max_dd)
    max_dds.sort()
    return MonteCarloReport(
        p50_drawdown=_percentile(max_dds, 0.50),
        p95_drawdown=_percentile(max_dds, 0.95),
        p99_drawdown=_percentile(max_dds, 0.99),
        ruin_probability=ruined / n_sims,
        n_sims=n_sims,
    )

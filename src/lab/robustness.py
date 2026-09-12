"""Robustez MVP: perturbaciones puntuales alrededor de baseline-v1 (Fase 17F).

Conjunto explícito y pequeño (una perturbación por vez, sin explosión
cartesiana, sin auto-optimización): ¿el comportamiento general es estable
alrededor del baseline? Reporta distribución y sensibilidad; nunca selecciona
"el mejor parámetro" ni promueve variantes.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any

from domain.trading.strategy import EmaRsiConfig

STABLE = "YES"
UNSTABLE = "NO"
INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class RobustnessVariant:
    """Una perturbación explícita de los parámetros del baseline."""

    name: str
    ema_fast: int
    ema_slow: int
    rsi_period: int
    rsi_exit: float


ROBUSTNESS_VARIANTS: tuple[RobustnessVariant, ...] = (
    RobustnessVariant("baseline", 20, 50, 14, 80.0),
    RobustnessVariant("ema-fast-18", 18, 50, 14, 80.0),
    RobustnessVariant("ema-fast-22", 22, 50, 14, 80.0),
    RobustnessVariant("ema-slow-45", 20, 45, 14, 80.0),
    RobustnessVariant("ema-slow-55", 20, 55, 14, 80.0),
    RobustnessVariant("rsi-exit-75", 20, 50, 14, 75.0),
    RobustnessVariant("rsi-exit-85", 20, 50, 14, 85.0),
)


def variant_config(variant: RobustnessVariant) -> EmaRsiConfig:
    """Mapea variante → config real de estrategia (sin valores nuevos)."""
    return EmaRsiConfig(
        ema_fast=variant.ema_fast,
        ema_slow=variant.ema_slow,
        rsi_period=variant.rsi_period,
        rsi_exit=variant.rsi_exit,
    )


def summarize_robustness(
    net_by_variant: dict[str, float], *, baseline_name: str = "baseline"
) -> dict[str, Any]:
    """Distribución y sensibilidad (puro, determinista; no selecciona ganador).

    Estable (YES) si el baseline es distinto de cero y todas las variantes
    comparten su signo (o son cero). Baseline cero → INCONCLUSIVE.
    """
    if baseline_name not in net_by_variant:
        raise ValueError(f"baseline ausente: {baseline_name}")
    ordered = sorted(net_by_variant.items())
    baseline = net_by_variant[baseline_name]
    if baseline == 0:
        stable = INCONCLUSIVE
    elif all(value == 0 or (value > 0) == (baseline > 0) for _, value in ordered):
        stable = STABLE
    else:
        stable = UNSTABLE
    values = [value for _, value in ordered]
    return {
        "baseline_net_pnl": baseline,
        "variants": len(ordered),
        "min_net_pnl": min(values),
        "max_net_pnl": max(values),
        "median_net_pnl": median(values),
        "stable": stable,
    }

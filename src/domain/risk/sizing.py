"""Sizing híbrido (PRD §21): intensidad LLM → monto real. El LLM nunca dimensiona.

qty = (capital * presupuesto_riesgo * escala_drawdown) / distancia_stop,
con distancia_stop = stop_atr_multiplier * ATR; el notional queda limitado por
max_position_allocation y por leverage=0 (sin apalancamiento).
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.risk.config import RiskConfig


@dataclass(frozen=True, slots=True)
class PositionSize:
    """Tamaño resultante tras las reglas de sizing."""

    quantity: float
    notional: float
    stop_distance: float
    risk_amount: float
    capped: bool


def compute_position_size(
    *,
    intensity: str | object,
    atr: float,
    price: float,
    current_drawdown: float,
    config: RiskConfig,
) -> PositionSize:
    """Calcula tamaño de posición determinista para una entrada en largo."""
    budget_pct = config.risk_budget_pct(intensity)
    stop_distance = config.stop_atr_multiplier * atr if atr > 0 else 0.0
    if stop_distance <= 0.0 or price <= 0.0:
        zero = 0.0
        return PositionSize(zero, zero, 0.0, 0.0, capped=False)

    scale = _drawdown_scale(current_drawdown, config.max_drawdown)
    risk_amount = config.capital * budget_pct * scale
    quantity = risk_amount / stop_distance

    max_notional = min(
        config.max_position_allocation * config.capital,
        config.capital * (1.0 - config.leverage),
    )
    notional = quantity * price
    capped = notional > max_notional
    if capped:
        quantity = max_notional / price
        notional = max_notional
    # Re-derivar riesgo efectivo tras el cap mantiene la trazabilidad del sizing.
    effective_risk = quantity * stop_distance
    return PositionSize(
        quantity=quantity,
        notional=notional,
        stop_distance=stop_distance,
        risk_amount=effective_risk,
        capped=capped,
    )


def _drawdown_scale(current_drawdown: float, max_drawdown: float) -> float:
    """Escala lineal 1→0 al acercarse al drawdown máximo (nunca amplifica)."""
    if current_drawdown <= 0.0:
        return 1.0
    if current_drawdown >= max_drawdown:
        return 0.0
    remaining = max_drawdown - current_drawdown
    return remaining / max_drawdown

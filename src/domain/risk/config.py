"""RiskConfig versionada (PRD §22) y sizing híbrido (PRD §21). Dominio puro.

El Risk Engine es la autoridad absoluta: estos parámetros son la única fuente de
verdad y el LLM no puede modificarlos. Cambiar valores ⇒ nueva `version`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RiskConfig:
    """Parámetros deterministas de riesgo, versionados para reproducibilidad."""

    capital: float = 1000.0
    max_position_allocation: float = 0.02
    max_daily_loss: float = 0.02
    max_drawdown: float = 0.05
    max_open_positions: int = 1
    leverage: float = 0.0
    stop_loss_required: bool = True
    stop_atr_multiplier: float = 2.0
    take_profit_r_multiple: float = 2.0
    trailing_atr_multiplier: float = 3.0
    low_risk_pct: float = 0.005
    medium_risk_pct: float = 0.01
    high_risk_pct: float = 0.02
    version: str = "risk-v1"

    def risk_budget_pct(self, intensity: str | object) -> float:
        """Presupuesto de riesgo (fracción del capital) según intensidad LLM.

        Cualquier valor no reconocido se trata como MEDIUM (fail-safe neutro).
        """
        key = str(getattr(intensity, "value", intensity)).lower()
        if key == "low":
            return self.low_risk_pct
        if key == "high":
            return self.high_risk_pct
        return self.medium_risk_pct

"""Presupuesto de coste LLM (PRD §60): límites y niveles de alerta. Dominio puro.

El presupuesto es inmutable: cada consumo devuelve una instancia nueva. Los niveles
de alerta permiten degradar el comportamiento (p. ej. forzar HOLD) antes de bloquear.
Un límite de ``0.0`` se interpreta como "sin límite" y jamás bloquea.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BudgetLevel(StrEnum):
    OK = "ok"
    ALERT_50 = "alert_50"
    ALERT_75 = "alert_75"
    ALERT_90 = "alert_90"
    BLOCKED = "blocked"


_SEVERITY: tuple[BudgetLevel, ...] = (
    BudgetLevel.OK,
    BudgetLevel.ALERT_50,
    BudgetLevel.ALERT_75,
    BudgetLevel.ALERT_90,
    BudgetLevel.BLOCKED,
)

_SEVERITY_INDEX: dict[BudgetLevel, int] = {level: i for i, level in enumerate(_SEVERITY)}


@dataclass(frozen=True, slots=True)
class Budget:
    """Límite de gasto en USD y consumo acumulado. Inmutable."""

    limit_usd: float
    consumed_usd: float = 0.0

    def ratio(self) -> float:
        """Fracción del límite consumida (``0.0`` si no hay límite)."""
        if self.limit_usd <= 0:
            return 0.0
        return self.consumed_usd / self.limit_usd

    def level(self) -> BudgetLevel:
        """Nivel de alerta según el ratio consumido."""
        ratio = self.ratio()
        if ratio >= 1.0:
            return BudgetLevel.BLOCKED
        if ratio >= 0.90:
            return BudgetLevel.ALERT_90
        if ratio >= 0.75:
            return BudgetLevel.ALERT_75
        if ratio >= 0.50:
            return BudgetLevel.ALERT_50
        return BudgetLevel.OK

    def is_blocked(self) -> bool:
        """Verdadero si el presupuesto alcanzó o superó el límite."""
        return self.level() is BudgetLevel.BLOCKED

    def consume(self, cost_usd: float) -> Budget:
        """Devuelve un nuevo presupuesto con el coste añadido (no muta)."""
        return Budget(self.limit_usd, self.consumed_usd + cost_usd)


@dataclass(frozen=True, slots=True)
class BudgetState:
    """Estado de presupuesto agregado: experimento (por ejecución) y mensual."""

    experiment: Budget
    monthly: Budget

    def record(self, cost_usd: float) -> BudgetState:
        """Registra un coste en ambos presupuestos, devolviendo un estado nuevo."""
        return BudgetState(
            experiment=self.experiment.consume(cost_usd),
            monthly=self.monthly.consume(cost_usd),
        )

    def is_blocked(self) -> bool:
        """Verdadero si cualquiera de los dos presupuestos está bloqueado."""
        return self.experiment.is_blocked() or self.monthly.is_blocked()


def max_level(a: BudgetLevel, b: BudgetLevel) -> BudgetLevel:
    """Devuelve el nivel más severo de los dos."""
    return a if _SEVERITY_INDEX[a] >= _SEVERITY_INDEX[b] else b

"""Monitor de coste LLM (PRD §60): acumulador de llamadas que impone los presupuestos.

Servicio de aplicación con estado: registra cada `LLMCallRecord` y aplica el consumo
sobre los presupuestos de dominio (`BudgetState`), devolviendo el nivel de alerta más
severo entre el presupuesto de experimento y el mensual.
"""

from __future__ import annotations

from domain.llm.budget import Budget, BudgetLevel, BudgetState, max_level
from domain.llm.call import LLMCallRecord


class CostMonitor:
    """Acumulador de llamadas LLM con presupuestos de experimento y mensual."""

    def __init__(self, experiment_budget_usd: float, monthly_budget_usd: float) -> None:
        self._state = BudgetState(
            experiment=Budget(limit_usd=experiment_budget_usd),
            monthly=Budget(limit_usd=monthly_budget_usd),
        )
        self._calls: list[LLMCallRecord] = []

    def record(self, call: LLMCallRecord) -> BudgetLevel:
        """Registra la llamada y devuelve el nivel de alerta más severo vigente."""
        self._calls.append(call)
        self._state = self._state.record(call.cost_usd)
        return max_level(self._state.experiment.level(), self._state.monthly.level())

    def is_blocked(self) -> bool:
        """Verdadero si cualquiera de los presupuestos está agotado."""
        return self._state.is_blocked()

    @property
    def total_cost_usd(self) -> float:
        """Coste total consumido del presupuesto mensual."""
        return self._state.monthly.consumed_usd

    @property
    def state(self) -> BudgetState:
        """Estado agregado de presupuestos vigente."""
        return self._state

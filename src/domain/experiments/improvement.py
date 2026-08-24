"""Improvement Proposal (PRD §36): sugerencia de mejora NUNCA auto-aplicada.

El flujo es: análisis histórico → propuesta → backtest/walk-forward →
comparación → aprobación humana → nueva versión. Esta entidad cubre el registro;
jamás muta estrategia ni riesgo por sí misma.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ImprovementProposal:
    """Propuesta de mejora inmutable con evidencia y estado de aprobación."""

    id: str
    title: str
    analysis: str
    proposed_change: dict[str, Any]
    evidence: dict[str, Any] = field(default_factory=dict)
    status: ProposalStatus = ProposalStatus.PENDING
    approval_id: str = ""
    rejection_reason: str = ""

    def with_status(
        self,
        status: ProposalStatus,
        *,
        approval_id: str,
        rejection_reason: str,
    ) -> ImprovementProposal:
        return replace(
            self,
            status=status,
            approval_id=approval_id,
            rejection_reason=rejection_reason,
        )

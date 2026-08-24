"""Workflow de aprobación humana de mejoras (PRD §36).

Las propuestas NUNCA se auto-aplican a producción: la aprobación solo cambia el
estado del registro. Aplicar el cambio (nueva versión de config/estrategia) es
un paso posterior, manual, con su propio gate.
"""

from __future__ import annotations

from typing import Literal

from domain.experiments.improvement import ImprovementProposal, ProposalStatus


class ApprovalWorkflow:
    """Registro en memoria de propuestas con decisión exclusivamente humana."""

    def __init__(self) -> None:
        self._proposals: dict[str, ImprovementProposal] = {}

    def submit(self, proposal: ImprovementProposal) -> None:
        if proposal.status is not ProposalStatus.PENDING:
            raise ValueError("una propuesta nueva debe nacer PENDING")
        self._proposals[proposal.id] = proposal

    def get(self, proposal_id: str) -> ImprovementProposal:
        return self._proposals[proposal_id]

    def list_pending(self) -> list[ImprovementProposal]:
        return [p for p in self._proposals.values() if p.status is ProposalStatus.PENDING]

    def _decide(
        self,
        proposal_id: str,
        by: Literal["human", "llm"],
        approval_id: str,
        rejection_reason: str,
        target_status: ProposalStatus,
    ) -> None:
        if by != "human" or not approval_id:
            raise PermissionError("solo una aprobación humana puede decidir mejoras")
        proposal = self._proposals[proposal_id]
        if proposal.status is not ProposalStatus.PENDING:
            raise ValueError(f"propuesta {proposal_id} ya decidida ({proposal.status.value})")
        self._proposals[proposal_id] = proposal.with_status(
            target_status, approval_id=approval_id, rejection_reason=rejection_reason
        )

    def approve(self, proposal_id: str, *, by: Literal["human", "llm"], approval_id: str) -> None:
        self._decide(proposal_id, by, approval_id, "", ProposalStatus.APPROVED)

    def reject(
        self, proposal_id: str, *, by: Literal["human", "llm"], approval_id: str, reason: str
    ) -> None:
        self._decide(proposal_id, by, approval_id, reason, ProposalStatus.REJECTED)

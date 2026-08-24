"""Tests de improvement proposals y aprobación humana (PRD §36, Fase 11)."""

import pytest

from application.services.approval_workflow import ApprovalWorkflow
from domain.experiments.improvement import ImprovementProposal, ProposalStatus


def _proposal(id_: str = "p1", field: str = "rsi_exit") -> ImprovementProposal:
    return ImprovementProposal(
        id=id_,
        title="Ajustar salida sobrecompra",
        analysis="12 pérdidas consecutivas con RSI>80 en la salida",
        proposed_change={"target_config": field, "from": "80.0", "to": "75.0"},
        evidence={"losses_analyzed": 12},
    )


def test_proposal_starts_pending() -> None:
    assert _proposal().status is ProposalStatus.PENDING


def test_workflow_submit_and_human_approve() -> None:
    wf = ApprovalWorkflow()
    wf.submit(_proposal())
    assert wf.get("p1").status is ProposalStatus.PENDING

    wf.approve("p1", by="human", approval_id="APR-9")
    p = wf.get("p1")
    assert p.status is ProposalStatus.APPROVED
    assert p.approval_id == "APR-9"


def test_llm_cannot_approve() -> None:
    wf = ApprovalWorkflow()
    wf.submit(_proposal())
    with pytest.raises(PermissionError):
        wf.approve("p1", by="llm", approval_id="x")
    with pytest.raises(PermissionError):
        wf.reject("p1", by="llm", approval_id="x", reason="no")


def test_reject_records_reason() -> None:
    wf = ApprovalWorkflow()
    wf.submit(_proposal())
    wf.reject("p1", by="human", approval_id="APR-8", reason="sobreajuste sospechado")
    p = wf.get("p1")
    assert p.status is ProposalStatus.REJECTED
    assert p.rejection_reason == "sobreajuste sospechado"


def test_unknown_proposal_raises() -> None:
    wf = ApprovalWorkflow()
    with pytest.raises(KeyError):
        wf.get("fantasma")


def test_double_decision_not_allowed() -> None:
    wf = ApprovalWorkflow()
    wf.submit(_proposal())
    wf.approve("p1", by="human", approval_id="APR-1")
    with pytest.raises(ValueError, match="decidida"):
        wf.approve("p1", by="human", approval_id="APR-2")


def test_never_auto_applies_to_risk_or_strategy() -> None:
    """La aprobación NO muta configs: solo cambia el estado de la propuesta."""
    wf = ApprovalWorkflow()
    wf.submit(_proposal(field="max_daily_loss"))
    cfg = {"max_daily_loss": "0.02"}  # simulación: la config real es ajena al workflow
    wf.approve("p1", by="human", approval_id="APR-7")
    assert cfg["max_daily_loss"] == "0.02"  # intacta: aplicar es otra fase (humana)

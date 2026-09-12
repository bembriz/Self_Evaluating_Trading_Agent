"""Tests fase 17G: máquina de promoción MVP-A hasta HOLDOUT_READY.

Promoción por evidencia, no por fases de software. STABLE_NEGATIVE es
rechazo. HOLDOUT_READY no consume el holdout (sigue PRISTINE).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lab.promote import (
    DRAFT,
    HOLDOUT_READY,
    PARITY_PASSED,
    ROBUSTNESS_PASSED,
    HoldoutReadinessEvidence,
    ParityEvidence,
    Promotion,
    PromotionRejected,
    RobustnessEvidence,
    StateTamperedError,
    UnsupportedStateError,
)

IDENTITY = "ab" * 32
SPEC = "cd" * 32
KERNEL = "ef" * 32
TS = "2026-09-12T05:00:00+00:00"
TS2 = "2026-09-12T05:00:01+00:00"
HOLDOUT_FILE = Path(__file__).resolve().parents[2] / "holdout" / "v1.state.json"

BASELINE_ROBUSTNESS = RobustnessEvidence(
    profitable_windows=0,
    losing_windows=3,
    expectancy=-0.06353337080013907,
    robustness_interpretation="STABLE_NEGATIVE",
    edge_present=False,
    promotable=False,
)


def _parity_evidence(runtime: bool = True, reproducible: bool = True) -> ParityEvidence:
    return ParityEvidence(runtime_parity=runtime, double_run_reproducibility=reproducible)


def _robust_evidence(**overrides: object) -> RobustnessEvidence:
    params: dict[str, object] = {
        "profitable_windows": 2,
        "losing_windows": 1,
        "expectancy": 0.5,
        "robustness_interpretation": "STABLE_POSITIVE",
        "edge_present": True,
        "promotable": True,
    }
    params.update(overrides)
    return RobustnessEvidence(**params)  # type: ignore[arg-type]


def _ready_evidence(**overrides: object) -> HoldoutReadinessEvidence:
    params: dict[str, object] = {
        "spec_id": SPEC,
        "strategy_identity": IDENTITY,
        "kernel_fingerprint": KERNEL,
        "split_version": 1,
        "holdout_state": "PRISTINE",
        "human_approved": True,
        "approver": "synthetic-human-gate",
    }
    params.update(overrides)
    return HoldoutReadinessEvidence(**params)  # type: ignore[arg-type]


def _at_parity(root: Path) -> Promotion:
    promotion = Promotion.create(root, strategy_identity=IDENTITY, spec_id_value=SPEC, timestamp=TS)
    return promotion.advance_to_parity(_parity_evidence(), timestamp=TS)


def _at_robustness(root: Path) -> Promotion:
    return _at_parity(root).advance_to_robustness(_robust_evidence(), timestamp=TS)


def _state_path(root: Path) -> Path:
    return root / f"{IDENTITY}.state.json"


def test_draft_to_parity_valid(tmp_path: Path) -> None:
    promotion = Promotion.create(
        tmp_path, strategy_identity=IDENTITY, spec_id_value=SPEC, timestamp=TS
    )
    assert promotion.state == DRAFT
    assert promotion.strategy_identity == IDENTITY
    assert promotion.spec_id == SPEC
    advanced = promotion.advance_to_parity(_parity_evidence(), timestamp=TS)
    assert advanced.state == PARITY_PASSED
    assert len(advanced.history) == 1
    assert _state_path(tmp_path).is_file()


def test_parity_without_research_is_valid(tmp_path: Path) -> None:
    advanced = _at_parity(tmp_path)
    assert advanced.state == PARITY_PASSED
    assert all(entry.reason != "research-note" for entry in advanced.history)


def test_research_note_does_not_change_state(tmp_path: Path) -> None:
    advanced = _at_parity(tmp_path)
    noted = advanced.add_research_note("idea: probar otra ventana", timestamp=TS2)
    assert noted.state == PARITY_PASSED
    assert len(noted.history) == len(advanced.history) + 1
    assert noted.history[-1].reason == "research-note"


def test_jump_draft_to_robustness_rejected(tmp_path: Path) -> None:
    promotion = Promotion.create(
        tmp_path, strategy_identity=IDENTITY, spec_id_value=SPEC, timestamp=TS
    )
    with pytest.raises(PromotionRejected, match="STATE_JUMP"):
        promotion.advance_to_robustness(_robust_evidence(), timestamp=TS)
    with pytest.raises(PromotionRejected, match="STATE_JUMP"):
        promotion.advance_to_parity(_parity_evidence(), timestamp=TS).advance_to_parity(
            _parity_evidence(), timestamp=TS
        )


def test_parity_to_robustness_with_valid_synthetic(tmp_path: Path) -> None:
    advanced = _at_parity(tmp_path).advance_to_robustness(_robust_evidence(), timestamp=TS)
    assert advanced.state == ROBUSTNESS_PASSED


def test_baseline_stable_negative_rejected(tmp_path: Path) -> None:
    advanced = _at_parity(tmp_path)
    with pytest.raises(PromotionRejected, match="NEGATIVE_WALK_FORWARD"):
        advanced.advance_to_robustness(BASELINE_ROBUSTNESS, timestamp=TS)
    assert Promotion.load(tmp_path, IDENTITY).state == PARITY_PASSED


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ({"robustness_interpretation": "STABLE_NEGATIVE"}, "NEGATIVE_WALK_FORWARD"),
        ({"edge_present": False}, "NO_DEMONSTRATED_EDGE"),
        ({"promotable": False}, "NOT_PROMOTABLE"),
        ({"profitable_windows": 0, "robustness_interpretation": "MIXED"}, "NEGATIVE_WALK_FORWARD"),
        ({"expectancy": None}, "NEGATIVE_WALK_FORWARD"),
        ({"expectancy": 0.0}, "NEGATIVE_WALK_FORWARD"),
    ],
)
def test_robustness_rejection_matrix(tmp_path: Path, field: object, reason: str) -> None:
    advanced = _at_parity(tmp_path)
    assert isinstance(field, dict)
    with pytest.raises(PromotionRejected, match=reason):
        advanced.advance_to_robustness(_robust_evidence(**field), timestamp=TS)


def test_parity_evidence_incomplete_rejected(tmp_path: Path) -> None:
    promotion = Promotion.create(
        tmp_path, strategy_identity=IDENTITY, spec_id_value=SPEC, timestamp=TS
    )
    with pytest.raises(PromotionRejected, match="PARITY_EVIDENCE_INCOMPLETE"):
        promotion.advance_to_parity(_parity_evidence(runtime=False), timestamp=TS)
    with pytest.raises(PromotionRejected, match="PARITY_EVIDENCE_INCOMPLETE"):
        promotion.advance_to_parity(_parity_evidence(reproducible=False), timestamp=TS)


def test_holdout_ready_with_complete_evidence(tmp_path: Path) -> None:
    before = HOLDOUT_FILE.read_bytes()
    advanced = _at_robustness(tmp_path).advance_to_holdout_ready(_ready_evidence(), timestamp=TS)
    assert advanced.state == HOLDOUT_READY
    assert HOLDOUT_FILE.read_bytes() == before
    import json

    assert json.loads(HOLDOUT_FILE.read_text(encoding="utf-8"))["state"] == "PRISTINE"


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ({"spec_id": "not-hex"}, "SHA-256"),
        ({"strategy_identity": "not-hex"}, "SHA-256"),
        ({"kernel_fingerprint": "not-hex"}, "SHA-256"),
        ({"split_version": 2}, "SPLIT_MISMATCH"),
        ({"holdout_state": "CONSUMED"}, "HOLDOUT_NOT_PRISTINE"),
        ({"human_approved": False}, "HUMAN_APPROVAL_REQUIRED"),
        ({"approver": "  "}, "HUMAN_APPROVAL_REQUIRED"),
    ],
)
def test_holdout_ready_rejection_matrix(tmp_path: Path, field: object, reason: str) -> None:
    advanced = _at_robustness(tmp_path)
    assert isinstance(field, dict)
    with pytest.raises(Exception, match=reason):
        advanced.advance_to_holdout_ready(_ready_evidence(**field), timestamp=TS)


def test_holdout_ready_from_wrong_state_rejected(tmp_path: Path) -> None:
    promotion = Promotion.create(
        tmp_path, strategy_identity=IDENTITY, spec_id_value=SPEC, timestamp=TS
    )
    with pytest.raises(PromotionRejected, match="STATE_JUMP"):
        promotion.advance_to_holdout_ready(_ready_evidence(), timestamp=TS)


@pytest.mark.parametrize("target", ["HOLDOUT_PASSED", "RELEASE_CANDIDATE", "PAPER_APPROVED"])
def test_post_mvp_a_states_rejected(tmp_path: Path, target: str) -> None:
    advanced = _at_robustness(tmp_path).advance_to_holdout_ready(_ready_evidence(), timestamp=TS)
    with pytest.raises(UnsupportedStateError, match="MVP-B"):
        advanced.request_post_mvp_a(target)


def test_unknown_state_rejected(tmp_path: Path) -> None:
    advanced = _at_parity(tmp_path)
    with pytest.raises(ValueError, match="unknown promotion state"):
        advanced.request_post_mvp_a("DEPLOYED")


def test_tampered_state_fails_closed(tmp_path: Path) -> None:
    _at_parity(tmp_path)
    path = _state_path(tmp_path)
    content = path.read_text(encoding="utf-8").replace(PARITY_PASSED, DRAFT)
    path.write_text(content, encoding="utf-8")
    with pytest.raises(StateTamperedError):
        Promotion.load(tmp_path, IDENTITY)


def test_history_is_append_only(tmp_path: Path) -> None:
    first = _at_parity(tmp_path)
    second = first.advance_to_robustness(_robust_evidence(), timestamp=TS2)
    assert len(second.history) == 2
    assert second.history[0] == first.history[0]
    assert (second.history[0].origin, second.history[0].target) == (DRAFT, PARITY_PASSED)


def test_same_evidence_is_deterministic(tmp_path: Path) -> None:
    first = Promotion.create(
        tmp_path / "a", strategy_identity=IDENTITY, spec_id_value=SPEC, timestamp=TS
    ).advance_to_parity(_parity_evidence(), timestamp=TS)
    second = Promotion.create(
        tmp_path / "b", strategy_identity=IDENTITY, spec_id_value=SPEC, timestamp=TS
    ).advance_to_parity(_parity_evidence(), timestamp=TS)
    assert (_state_path(tmp_path / "a")).read_bytes() == (_state_path(tmp_path / "b")).read_bytes()
    assert first.history == second.history


def test_create_validates_and_rejects_duplicates(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        Promotion.create(tmp_path, strategy_identity="bad", spec_id_value=SPEC, timestamp=TS)
    with pytest.raises(ValueError, match="SHA-256"):
        Promotion.create(tmp_path, strategy_identity=IDENTITY, spec_id_value="bad", timestamp=TS)
    Promotion.create(tmp_path, strategy_identity=IDENTITY, spec_id_value=SPEC, timestamp=TS)
    with pytest.raises(PromotionRejected, match="PROMOTION_EXISTS"):
        Promotion.create(tmp_path, strategy_identity=IDENTITY, spec_id_value=SPEC, timestamp=TS)
    with pytest.raises(FileNotFoundError, match="desconocida"):
        Promotion.load(tmp_path, "ff" * 32)
    with pytest.raises(ValueError, match="SHA-256"):
        Promotion.load(tmp_path, "bad")


def test_baseline_expected_result() -> None:
    assert BASELINE_ROBUSTNESS.profitable_windows == 0
    assert BASELINE_ROBUSTNESS.losing_windows == 3
    assert BASELINE_ROBUSTNESS.expectancy == -0.06353337080013907
    assert BASELINE_ROBUSTNESS.robustness_interpretation == "STABLE_NEGATIVE"
    assert BASELINE_ROBUSTNESS.edge_present is False
    assert BASELINE_ROBUSTNESS.promotable is False

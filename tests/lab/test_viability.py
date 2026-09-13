"""Phase 19C unit contract for the Absolute Viability Gate and eligibility guard."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from lab.promote import (
    DRAFT,
    HOLDOUT_READY,
    PARITY_PASSED,
    ROBUSTNESS_PASSED,
    ParityEvidence,
    Promotion,
)
from lab.viability import (
    AbsoluteViabilityEvidence,
    guarded_walk_forward_open,
    walk_forward_eligible,
)

REPO = Path(__file__).resolve().parents[2]
HOLDOUT_FILE = REPO / "holdout" / "v1.state.json"

PASSING = AbsoluteViabilityEvidence(net_pnl=1.0, expectancy=0.5, profit_factor=1.5)


def test_absolute_viability_passes_with_positive_finite_metrics() -> None:
    assert PASSING.passed is True


@pytest.mark.parametrize(
    "net_pnl, expectancy, profit_factor",
    (
        (0.0, 0.5, 1.5),
        (1.0, 0.0, 1.5),
        (1.0, 0.5, 1.0),
        (-1.0, 0.5, 1.5),
        (1.0, -0.5, 1.5),
        (1.0, 0.5, 0.9),
    ),
)
def test_absolute_viability_fails_on_boundaries_and_negatives(
    net_pnl: float, expectancy: float, profit_factor: float
) -> None:
    evidence = AbsoluteViabilityEvidence(net_pnl, expectancy, profit_factor)
    assert evidence.passed is False


@pytest.mark.parametrize(
    "net_pnl, expectancy, profit_factor",
    (
        (None, 0.5, 1.5),
        (1.0, None, 1.5),
        (1.0, 0.5, None),
        (math.nan, 0.5, 1.5),
        (1.0, math.nan, 1.5),
        (1.0, 0.5, math.nan),
        (math.inf, 0.5, 1.5),
        (1.0, math.inf, 1.5),
        (1.0, 0.5, math.inf),
        (-math.inf, 0.5, 1.5),
        (1.0, -math.inf, 1.5),
        (1.0, 0.5, -math.inf),
    ),
)
def test_absolute_viability_fails_closed_on_undefined_or_non_finite(
    net_pnl: float | None, expectancy: float | None, profit_factor: float | None
) -> None:
    evidence = AbsoluteViabilityEvidence(net_pnl, expectancy, profit_factor)
    assert evidence.passed is False


def test_absolute_viability_from_metrics_fails_closed_on_missing_keys() -> None:
    assert AbsoluteViabilityEvidence.from_metrics({}).passed is False
    assert AbsoluteViabilityEvidence.from_metrics({"net_pnl": 1.0}).passed is False
    assert (
        AbsoluteViabilityEvidence.from_metrics(
            {"net_pnl": 1.0, "expectancy": 0.5, "profit_factor": 1.5}
        ).passed
        is True
    )
    # Non-numeric values are treated as undefined.
    assert (
        AbsoluteViabilityEvidence.from_metrics(
            {"net_pnl": "1.0", "expectancy": True, "profit_factor": None}
        ).passed
        is False
    )


def test_absolute_viability_is_deterministic_and_side_effect_free() -> None:
    assert PASSING.passed == PASSING.passed
    assert AbsoluteViabilityEvidence(1.0, 0.5, 1.5) == AbsoluteViabilityEvidence(1.0, 0.5, 1.5)


@pytest.mark.parametrize(
    "development_result, evidence, expected",
    (
        ("IMPROVED", PASSING, True),
        ("IMPROVED", AbsoluteViabilityEvidence(1.0, 0.5, 1.0), False),
        ("MIXED", PASSING, False),
        ("MIXED", AbsoluteViabilityEvidence(1.0, 0.5, 1.0), False),
        ("NOT_IMPROVED", PASSING, False),
        ("NOT_IMPROVED", AbsoluteViabilityEvidence(1.0, 0.5, 1.0), False),
    ),
)
def test_walk_forward_eligibility_truth_table(
    development_result: str, evidence: AbsoluteViabilityEvidence, expected: bool
) -> None:
    assert walk_forward_eligible(development_result, evidence) is expected


MISSING_REPO = Path("/nonexistent-phase19c-repo")


def _guarded(**overrides: object) -> object:
    params: dict[str, object] = {
        "development_result": "IMPROVED",
        "absolute_viability": PASSING,
        "human_authorized": True,
        "repo_root": MISSING_REPO,
        "symbol": "ETHUSDT",
        "timeframe": "15m",
        "row_start": 62208,
        "row_end": 62220,
    }
    params.update(overrides)
    return guarded_walk_forward_open(**params)  # type: ignore[arg-type]


def test_ineligible_candidate_never_opens_walk_forward() -> None:
    # Nonexistent repo: if the guard tried to open the adapter it would raise.
    assert _guarded(development_result="MIXED") is None


def test_failed_viability_never_opens_walk_forward() -> None:
    failing = AbsoluteViabilityEvidence(net_pnl=1.0, expectancy=0.5, profit_factor=1.0)
    assert _guarded(absolute_viability=failing) is None


def test_eligible_but_unauthorized_never_opens_walk_forward() -> None:
    assert _guarded(human_authorized=False) is None


def test_eligible_and_authorized_opens_walk_forward(synthetic_frozen_repo: Path) -> None:
    adapter = _guarded(repo_root=synthetic_frozen_repo)
    assert adapter is not None
    assert len(adapter) == 12  # type: ignore[arg-type]


def test_parity_passed_can_coexist_with_viability_failure(tmp_path: Path) -> None:
    promotion = Promotion.create(
        tmp_path / "promotions",
        strategy_identity="ab" * 32,
        spec_id_value="cd" * 32,
        timestamp="2026-09-13T01:00:00+00:00",
    )
    promotion = promotion.advance_to_parity(
        ParityEvidence(runtime_parity=True, double_run_reproducibility=True),
        timestamp="2026-09-13T01:00:01+00:00",
    )
    assert promotion.state == PARITY_PASSED

    failing = AbsoluteViabilityEvidence(net_pnl=-1.0, expectancy=-0.5, profit_factor=0.4)
    assert walk_forward_eligible("IMPROVED", failing) is False
    assert _guarded(absolute_viability=failing) is None
    # Parity semantics unchanged: passing viability does not alter the state.
    assert promotion.state == PARITY_PASSED


def test_no_new_promotion_states_exist() -> None:
    assert (DRAFT, PARITY_PASSED, ROBUSTNESS_PASSED, HOLDOUT_READY) == (
        "DRAFT",
        "PARITY_PASSED",
        "ROBUSTNESS_PASSED",
        "HOLDOUT_READY",
    )


def test_holdout_remains_pristine_and_untouched() -> None:
    import json

    before = HOLDOUT_FILE.read_bytes()
    assert json.loads(before.decode("utf-8"))["state"] == "PRISTINE"
    # Running the guard never reads FINAL_HOLDOUT.
    assert _guarded(development_result="MIXED", human_authorized=False) is None
    assert HOLDOUT_FILE.read_bytes() == before

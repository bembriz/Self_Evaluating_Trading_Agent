#!/usr/bin/env python3
"""Phase 19C — mechanical evidence for the Absolute Viability Gate."""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from typing import Any

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

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "phases" / "19C" / "evidence" / "viability-gate.json"
PASSING = AbsoluteViabilityEvidence(net_pnl=1.0, expectancy=0.5, profit_factor=1.5)


def _jsonable(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def absolute_viability_table() -> list[dict[str, Any]]:
    cases = (
        (1.0, 0.5, 1.5, True),
        (0.0, 0.5, 1.5, False),
        (1.0, 0.0, 1.5, False),
        (1.0, 0.5, 1.0, False),
        (-1.0, 0.5, 1.5, False),
        (None, 0.5, 1.5, False),
        (math.nan, 0.5, 1.5, False),
        (math.inf, 0.5, 1.5, False),
        (-math.inf, 0.5, 1.5, False),
        (1.0, 0.5, math.inf, False),
    )
    return [
        {
            "net_pnl": _jsonable(net),
            "expectancy": _jsonable(exp),
            "profit_factor": _jsonable(pf),
            "expected": expected,
            "actual": AbsoluteViabilityEvidence(net, exp, pf).passed,
        }
        for net, exp, pf, expected in cases
    ]


def eligibility_table() -> list[dict[str, Any]]:
    failing = AbsoluteViabilityEvidence(1.0, 0.5, 1.0)
    cases = (
        ("IMPROVED", PASSING, True),
        ("IMPROVED", failing, False),
        ("MIXED", PASSING, False),
        ("MIXED", failing, False),
        ("NOT_IMPROVED", PASSING, False),
        ("NOT_IMPROVED", failing, False),
    )
    return [
        {
            "development_result": result,
            "absolute_viability": "PASS" if evidence.passed else "FAIL",
            "expected": expected,
            "actual": walk_forward_eligible(result, evidence),
        }
        for result, evidence, expected in cases
    ]


def parity_compatibility() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        promotion = Promotion.create(
            Path(tmp),
            strategy_identity="ab" * 32,
            spec_id_value="cd" * 32,
            timestamp="2026-09-13T01:00:00+00:00",
        )
        promotion = promotion.advance_to_parity(
            ParityEvidence(runtime_parity=True, double_run_reproducibility=True),
            timestamp="2026-09-13T01:00:01+00:00",
        )
        state_after_parity = promotion.state
    return {
        "parity_state": state_after_parity,
        "states": [DRAFT, PARITY_PASSED, ROBUSTNESS_PASSED, HOLDOUT_READY],
        "parity_semantics_unchanged": state_after_parity == PARITY_PASSED,
    }


def zero_walk_forward_reads() -> dict[str, Any]:
    missing = Path("/nonexistent-phase19c-repo")
    ineligible = guarded_walk_forward_open(
        development_result="MIXED",
        absolute_viability=PASSING,
        human_authorized=True,
        repo_root=missing,
        symbol="ETHUSDT",
        timeframe="15m",
        row_start=62208,
        row_end=62220,
    )
    unauthorized = guarded_walk_forward_open(
        development_result="IMPROVED",
        absolute_viability=PASSING,
        human_authorized=False,
        repo_root=missing,
        symbol="ETHUSDT",
        timeframe="15m",
        row_start=62208,
        row_end=62220,
    )
    authorized_attempted_io = False
    try:
        guarded_walk_forward_open(
            development_result="IMPROVED",
            absolute_viability=PASSING,
            human_authorized=True,
            repo_root=missing,
            symbol="ETHUSDT",
            timeframe="15m",
            row_start=62208,
            row_end=62220,
        )
    except (FileNotFoundError, ValueError):
        authorized_attempted_io = True
    return {
        "ineligible_result": ineligible,
        "unauthorized_result": unauthorized,
        "authorized_attempted_io": authorized_attempted_io,
        "zero_reads_for_ineligible": ineligible is None and unauthorized is None,
    }


def build_evidence() -> dict[str, Any]:
    return {
        "PHASE": "19C",
        "ABSOLUTE_VIABILITY_TRUTH_TABLE": absolute_viability_table(),
        "ELIGIBILITY_TRUTH_TABLE": eligibility_table(),
        "PARITY_COMPATIBILITY": parity_compatibility(),
        "ZERO_WALK_FORWARD_READS": zero_walk_forward_reads(),
    }


def main() -> int:
    report = build_evidence()
    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(_jsonable(report), indent=2, sort_keys=True) + "\n"
    DEFAULT_OUTPUT.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

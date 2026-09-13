"""Absolute Viability Gate + pre-walk-forward eligibility guard (Phase 19C).

Prospective policy only: this module does not modify historical results, the
Phase 17G promotion state machine, or `ParityEvidence` semantics.

Absolute viability PASS requires all three DEVELOPMENT metrics to be finite,
defined and strictly positive (profit factor strictly greater than 1.0). Any
missing/None/NaN/±inf metric fails closed, including `profit_factor == inf`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from lab.frozen_dataset import FrozenDatasetAdapter

DEVELOPMENT_IMPROVED = "IMPROVED"


def _as_optional_float(value: object) -> float | None:
    """Coerce a metric to float, returning None for missing/non-numeric values."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _is_finite_positive(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0.0


def _is_finite_above_one(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 1.0


@dataclass(frozen=True, slots=True)
class AbsoluteViabilityEvidence:
    """Frozen DEVELOPMENT metrics for the Absolute Viability Gate."""

    net_pnl: float | None
    expectancy: float | None
    profit_factor: float | None

    @property
    def passed(self) -> bool:
        """True iff all three metrics are finite/defined and strictly positive."""
        return (
            _is_finite_positive(self.net_pnl)
            and _is_finite_positive(self.expectancy)
            and _is_finite_above_one(self.profit_factor)
        )

    @classmethod
    def from_metrics(cls, metrics: Mapping[str, object]) -> AbsoluteViabilityEvidence:
        """Build evidence from a metrics mapping; missing/invalid keys fail closed."""
        return cls(
            net_pnl=_as_optional_float(metrics.get("net_pnl")),
            expectancy=_as_optional_float(metrics.get("expectancy")),
            profit_factor=_as_optional_float(metrics.get("profit_factor")),
        )


def walk_forward_eligible(
    development_result: str, absolute_viability: AbsoluteViabilityEvidence
) -> bool:
    """Eligibility: IMPROVED relative result AND absolute viability PASS."""
    return development_result == DEVELOPMENT_IMPROVED and absolute_viability.passed


def guarded_walk_forward_open(
    *,
    development_result: str,
    absolute_viability: AbsoluteViabilityEvidence,
    human_authorized: bool,
    repo_root: Path,
    symbol: str,
    timeframe: str,
    row_start: int,
    row_end: int,
) -> FrozenDatasetAdapter | None:
    """Enforce eligibility and authorization BEFORE any WALK_FORWARD dataset IO.

    This is the only production/lab caller of the private authorized opener
    `FrozenDatasetAdapter._from_repo_authorized_walk_forward`. It validates the
    relative result, the absolute viability evidence and explicit human
    authorization first; an ineligible or unauthorized candidate returns None
    and performs zero adapter creation and zero dataset reads.
    """
    if not walk_forward_eligible(development_result, absolute_viability):
        return None
    if not human_authorized:
        return None
    return FrozenDatasetAdapter._from_repo_authorized_walk_forward(
        repo_root,
        symbol=symbol,
        timeframe=timeframe,
        row_start=row_start,
        row_end=row_end,
    )

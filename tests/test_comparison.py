"""Tests de comparación con baselines y protocolo holdout (PRD §47)."""

import pytest

from domain.evaluation.comparison import (
    BaselineComparison,
    compare_baselines,
    degradation_train_val_holdout,
)


def test_comparison_all_beaten_is_pass() -> None:
    r: BaselineComparison = compare_baselines(
        strategy_net=150.0, deterministic_net=80.0, ml_net=100.0, buy_hold_net=-20.0
    )
    assert r.beats_deterministic and r.beats_ml and r.beats_buy_hold
    assert r.verdict == "PASS"


def test_comparison_fails_if_any_baseline_not_beaten() -> None:
    r = compare_baselines(
        strategy_net=90.0, deterministic_net=80.0, ml_net=100.0, buy_hold_net=-20.0
    )
    assert r.beats_deterministic is True
    assert r.beats_ml is False
    assert r.verdict == "FAIL"


def test_degradation_monotonic_is_healthy() -> None:
    r = degradation_train_val_holdout(train=1.5, validation=1.2, holdout=0.9)
    assert r.holdout_retention == pytest.approx(0.6)
    assert r.is_overfit is False


def test_degradation_severe_drop_flags_overfit() -> None:
    r = degradation_train_val_holdout(train=2.0, validation=0.4, holdout=-0.5)
    assert r.is_overfit is True
    assert r.holdout_negative is True


def test_degradation_zero_train_guard() -> None:
    r = degradation_train_val_holdout(train=0.0, validation=1.0, holdout=1.0)
    assert r.holdout_retention == 0.0
    assert r.is_overfit is True  # sin edge en train pero sí fuera ⇒ inestable

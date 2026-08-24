"""Comparación con baselines obligatorios y protocolo holdout (PRD §42, §47).

La estrategia debe superar al baseline determinista, al ML y compararse con
Buy & Hold — todo NETO. La degradación train→validation→holdout detecta
overfitting; el holdout se evalúa UNA sola vez, al final.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BaselineComparison:
    strategy_net: float
    deterministic_net: float
    ml_net: float
    buy_hold_net: float
    beats_deterministic: bool
    beats_ml: bool
    beats_buy_hold: bool
    verdict: str


def compare_baselines(
    *,
    strategy_net: float,
    deterministic_net: float,
    ml_net: float,
    buy_hold_net: float,
) -> BaselineComparison:
    beats_det = strategy_net > deterministic_net
    beats_ml = strategy_net > ml_net
    beats_bh = strategy_net > buy_hold_net
    return BaselineComparison(
        strategy_net=strategy_net,
        deterministic_net=deterministic_net,
        ml_net=ml_net,
        buy_hold_net=buy_hold_net,
        beats_deterministic=beats_det,
        beats_ml=beats_ml,
        beats_buy_hold=beats_bh,
        verdict="PASS" if (beats_det and beats_ml and beats_bh) else "FAIL",
    )


@dataclass(frozen=True, slots=True)
class DegradationReport:
    train_metric: float
    validation_metric: float
    holdout_metric: float
    holdout_retention: float  # holdout / train, acotado a [0, 1]
    holdout_negative: bool
    is_overfit: bool


def degradation_train_val_holdout(
    *,
    train: float,
    validation: float,
    holdout: float,
    min_retention: float = 0.5,
) -> DegradationReport:
    """Overfitting si el holdout retiene poco del edge de train o se vuelve negativo."""
    retention = max(0.0, min(holdout / train, 1.0)) if train > 0.0 else 0.0
    overfit = holdout <= 0.0 or retention < min_retention or (train > 0.0 and validation <= 0.0)
    return DegradationReport(
        train_metric=train,
        validation_metric=validation,
        holdout_metric=holdout,
        holdout_retention=retention,
        holdout_negative=holdout <= 0.0,
        is_overfit=overfit,
    )

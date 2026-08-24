"""Tests anti-lookahead del pipeline ML (PRD §34).

La feature en `t` usa solo datos ≤ `t`; el entrenamiento walk-forward usa solo pasado;
envenenar velas futuras no debe alterar features, predicciones ni equity en el pasado.
"""

from __future__ import annotations

from application.services.ml_pipeline import MlBaselineConfig, run_ml_baseline
from domain.experiments.features import build_features
from domain.market.candle import Candle


def _series(n: int) -> list[Candle]:
    out: list[Candle] = []
    prev = 100.0
    for i in range(n):
        close = prev * (1.0 + 0.0005 + (0.003 if i % 30 < 15 else -0.003))
        out.append(
            Candle(i * 3600_000, prev, max(prev, close), min(prev, close), close, 1.0, close)
        )
        prev = close
    return out


def _poisoned(i: int) -> Candle:
    return Candle(i * 3600_000, 10**9, 10**9, 10**9, 10**9, 0.0, 0.0)


def test_features_invariant_to_future_poisoning() -> None:
    candles = _series(300)
    base = build_features(candles)
    poison_at = 150
    poisoned = candles[:poison_at] + [_poisoned(i) for i in range(poison_at, 300)]
    poisoned_m = build_features(poisoned)
    # Filas con índice de barra < poison_at-1 son idénticas (la etiqueta de la última
    # fila común usa close[poison_at], que sí cambia).
    cutoff = poison_at - 1
    base_idx = [i for i in base.indices if i < cutoff]
    poisoned_idx = [i for i in poisoned_m.indices if i < cutoff]
    assert base_idx == poisoned_idx
    assert base.features[: len(base_idx)] == poisoned_m.features[: len(poisoned_idx)]


def test_pipeline_equity_prefix_invariant() -> None:
    candles = _series(300)
    cfg = MlBaselineConfig(initial_train=50, val_size=30, step=30)
    base = run_ml_baseline(candles, cfg)
    poison_at = 150
    poisoned = candles[:poison_at] + [_poisoned(i) for i in range(poison_at, 300)]
    poisoned_result = run_ml_baseline(poisoned, cfg)
    assert poisoned_result.equity_curve[:poison_at] == base.equity_curve[:poison_at]


def test_walk_forward_train_strictly_before_val() -> None:
    from domain.experiments.walk_forward import WalkForwardConfig, WalkForwardSplitter

    splitter = WalkForwardSplitter(WalkForwardConfig(initial_train=60, val_size=20, step=20))
    for val_start, val_end in splitter.windows(400):
        assert val_start >= 60  # train = [0, val_start)
        assert val_start < val_end

"""Pipeline ML baseline reproducible (PRD §30, §39, §43). Orquesta dominio puro.

Flujo: `build_features` (causal) → walk-forward cronológico → entrenar/predicción con
`LogisticRegression` → acciones → `BacktestEngine` (reusado) → métricas comparables +
métricas de clasificación. `experiment_id` inmutable derivado de la configuración.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from application.services.backtest_engine import BacktestEngine
from domain.evaluation.metrics import PerformanceMetrics
from domain.experiments.experiment import ExperimentMetadata, build_experiment_id
from domain.experiments.features import FeatureMatrix, build_features
from domain.experiments.logistic_regression import LogisticRegression
from domain.experiments.walk_forward import WalkForwardConfig, WalkForwardSplitter
from domain.market.candle import Candle
from domain.trading.fill import FillModel
from domain.trading.signal import Action
from domain.trading.strategy import PrecomputedStrategy


@dataclass(frozen=True, slots=True)
class MlBaselineConfig:
    initial_train: int
    val_size: int
    step: int
    holdout_size: int = 0
    buy_threshold: float = 0.55
    sell_threshold: float = 0.45
    learning_rate: float = 1.0
    max_iter: int = 500
    l2: float = 0.0
    feature_config_version: str = "v1"


@dataclass(frozen=True, slots=True)
class ClassificationMetrics:
    n: int
    accuracy: float | None
    precision: float | None
    recall: float | None


@dataclass(frozen=True, slots=True)
class MlBaselineResult:
    metrics: PerformanceMetrics
    classification: ClassificationMetrics
    experiment_id: str
    equity_curve: tuple[float, ...]


def _classification(y_true: Sequence[int], y_pred: Sequence[int]) -> ClassificationMetrics:
    n = len(y_true)
    if n == 0:
        return ClassificationMetrics(n=0, accuracy=None, precision=None, recall=None)
    tp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == 1 and p == 0)
    accuracy = (n - sum(1 for t, p in zip(y_true, y_pred, strict=True) if t != p)) / n
    precision = tp / (tp + fp) if (tp + fp) > 0 else None
    recall = tp / (tp + fn) if (tp + fn) > 0 else None
    return ClassificationMetrics(n=n, accuracy=accuracy, precision=precision, recall=recall)


def _experiment_id(config: MlBaselineConfig, dataset_version: str, git_commit: str) -> str:
    meta = ExperimentMetadata(
        git_commit=git_commit,
        dataset_version=dataset_version,
        strategy_version="ml-logistic-v1",
        feature_config_version=config.feature_config_version,
        fees_model_version="bybit-spot-v1",
        slippage_model_version="conservative-v1",
        random_seed=0,
        params=(
            ("initial_train", str(config.initial_train)),
            ("val_size", str(config.val_size)),
            ("step", str(config.step)),
            ("holdout_size", str(config.holdout_size)),
            ("buy_threshold", repr(config.buy_threshold)),
            ("sell_threshold", repr(config.sell_threshold)),
            ("learning_rate", repr(config.learning_rate)),
            ("max_iter", str(config.max_iter)),
            ("l2", repr(config.l2)),
        ),
    )
    return build_experiment_id(meta)


def run_ml_baseline(
    candles: Sequence[Candle],
    config: MlBaselineConfig,
    dataset_version: str = "",
    git_commit: str = "",
    initial_cash: float = 1000.0,
    periods_per_year: float = 8760.0,
) -> MlBaselineResult:
    fm: FeatureMatrix = build_features(candles)
    n_bars = len(candles)
    probs: list[float | None] = [None] * n_bars

    splitter = WalkForwardSplitter(
        WalkForwardConfig(
            initial_train=config.initial_train,
            val_size=config.val_size,
            step=config.step,
            holdout_size=config.holdout_size,
        )
    )
    y_true: list[int] = []
    y_pred: list[int] = []
    m = len(fm.indices)
    for val_start, val_end in splitter.windows(m):
        model = LogisticRegression(
            learning_rate=config.learning_rate, max_iter=config.max_iter, l2=config.l2
        )
        model.fit(fm.features[:val_start], fm.labels[:val_start])
        val_probs = model.predict_proba(fm.features[val_start:val_end])
        for row in range(val_start, val_end):
            bar = fm.indices[row]
            probs[bar] = val_probs[row - val_start]
            y_true.append(fm.labels[row])
            y_pred.append(1 if val_probs[row - val_start] >= 0.5 else 0)

    actions = [_action(p, config) for p in probs]

    engine = BacktestEngine(
        PrecomputedStrategy(actions),
        FillModel(),
        initial_cash=initial_cash,
        periods_per_year=periods_per_year,
    )
    result = engine.run(candles)

    return MlBaselineResult(
        metrics=result.metrics,
        classification=_classification(y_true, y_pred),
        experiment_id=_experiment_id(config, dataset_version, git_commit),
        equity_curve=result.equity_curve,
    )


def _action(prob: float | None, config: MlBaselineConfig) -> Action:
    if prob is None:
        return Action.HOLD
    if prob >= config.buy_threshold:
        return Action.BUY
    if prob <= config.sell_threshold:
        return Action.SELL
    return Action.HOLD

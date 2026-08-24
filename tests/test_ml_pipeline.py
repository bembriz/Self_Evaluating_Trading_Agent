from application.services.ml_pipeline import MlBaselineConfig, run_ml_baseline
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


def _config() -> MlBaselineConfig:
    return MlBaselineConfig(initial_train=200, val_size=100, step=100)


def test_pipeline_produces_metrics_and_id() -> None:
    result = run_ml_baseline(_series(600), _config())
    assert result.experiment_id
    assert result.metrics.trades >= 0
    assert result.classification.n > 0
    assert result.classification.accuracy is not None


def test_pipeline_deterministic() -> None:
    candles = _series(600)
    r1 = run_ml_baseline(candles, _config())
    r2 = run_ml_baseline(candles, _config())
    assert r1.experiment_id == r2.experiment_id
    assert r1.metrics == r2.metrics
    assert r1.classification == r2.classification


def test_experiment_id_changes_with_config() -> None:
    candles = _series(600)
    a = run_ml_baseline(candles, _config()).experiment_id
    b = run_ml_baseline(
        candles, MlBaselineConfig(initial_train=200, val_size=100, step=100, buy_threshold=0.6)
    ).experiment_id
    assert a != b


def test_classification_metrics_known_case() -> None:
    from application.services.ml_pipeline import _classification

    m = _classification([1, 1, 0, 0], [1, 0, 0, 0])
    assert m.n == 4
    assert m.accuracy == 0.75
    assert m.precision == 1.0
    assert m.recall == 0.5


def test_empty_classification() -> None:
    from application.services.ml_pipeline import _classification

    m = _classification([], [])
    assert m.n == 0
    assert m.accuracy is None

from domain.experiments.features import build_features
from domain.market.candle import Candle


def _series(n: int) -> list[Candle]:
    out: list[Candle] = []
    prev = 100.0
    for i in range(n):
        close = prev * (1.0 + (0.001 if i % 2 == 0 else -0.0005))
        out.append(
            Candle(i * 3600_000, prev, max(prev, close), min(prev, close), close, 1.0, close)
        )
        prev = close
    return out


def test_labels_are_next_return_sign() -> None:
    candles = _series(100)
    m = build_features(candles)
    for row, t in enumerate(m.indices):
        expected = 1 if candles[t + 1].close > candles[t].close else 0
        assert m.labels[row] == expected


def test_features_do_not_change_when_future_poisoned() -> None:
    candles = _series(150)
    base = build_features(candles)
    poisoned = candles[:100] + [
        Candle(i * 3600_000, 10**9, 10**9, 10**9, 10**9, 0.0, 0.0) for i in range(100, 150)
    ]
    poisoned_m = build_features(poisoned)
    # Las filas correspondientes a barras < 100 son idénticas (la última fila del base
    # usa la barra 99 como feature; la etiqueta de esa fila usa close[100], por eso
    # comparamos solo filas con índice < 99).
    cutoff = 99
    base_idx = [i for i in base.indices if i < cutoff]
    poisoned_idx = [i for i in poisoned_m.indices if i < cutoff]
    assert base_idx == poisoned_idx
    assert base.features[: len(base_idx)] == poisoned_m.features[: len(poisoned_idx)]


def test_warmup_bars_excluded() -> None:
    candles = _series(50)
    m = build_features(candles)
    assert m.indices[0] == 14  # RSI(14) es la restricción de warmup
    assert len(m.indices) == len(m.features) == len(m.labels)


def test_aligned_lengths() -> None:
    candles = _series(120)
    m = build_features(candles)
    assert len(m.indices) == len(m.features) == len(m.labels)
    assert all(len(f) == 4 for f in m.features)


def test_empty_short_series() -> None:
    m = build_features(_series(5))
    assert m.indices == ()
    assert m.features == ()
    assert m.labels == ()

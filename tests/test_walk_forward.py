import pytest

from domain.experiments.walk_forward import WalkForwardConfig, WalkForwardSplitter


def test_windows_are_chronological_and_expanding() -> None:
    splitter = WalkForwardSplitter(WalkForwardConfig(initial_train=100, val_size=50, step=50))
    windows = splitter.windows(300)
    assert windows == [(100, 150), (150, 200), (200, 250), (250, 300)]
    for val_start, val_end in windows:
        assert val_start < val_end


def test_holdout_is_excluded() -> None:
    splitter = WalkForwardSplitter(
        WalkForwardConfig(initial_train=100, val_size=50, step=50, holdout_size=60)
    )
    windows = splitter.windows(300)
    # limit = 300 - 60 = 240; la última ventana debe terminar en <= 240.
    assert all(val_end <= 240 for _, val_end in windows)
    assert windows[-1][1] <= 240


def test_short_series_yields_no_windows() -> None:
    splitter = WalkForwardSplitter(WalkForwardConfig(initial_train=100, val_size=50, step=50))
    assert splitter.windows(80) == []


def test_train_is_always_before_validation() -> None:
    splitter = WalkForwardSplitter(WalkForwardConfig(initial_train=40, val_size=20, step=10))
    for val_start, val_end in splitter.windows(200):
        assert val_start >= 0  # train = [0, val_start), siempre anterior
        assert val_start < val_end


def test_invalid_config_raises() -> None:
    with pytest.raises(ValueError):
        WalkForwardSplitter(WalkForwardConfig(initial_train=0, val_size=10, step=10))
    with pytest.raises(ValueError):
        WalkForwardSplitter(
            WalkForwardConfig(initial_train=10, val_size=10, step=10, holdout_size=-1)
        )

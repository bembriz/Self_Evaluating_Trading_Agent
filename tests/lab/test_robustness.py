"""Tests fase 17F: robustez MVP (variantes explícitas, sin minería).

Reporta distribución y sensibilidad; nunca selecciona ni promueve variantes.
"""

from __future__ import annotations

from pathlib import Path

from application.services.paper_engine import PaperEngine
from domain.risk.config import RiskConfig
from domain.trading.strategy import EmaRsiBaseline, EmaRsiConfig
from lab.frozen_dataset import FrozenDatasetAdapter
from lab.robustness import (
    INCONCLUSIVE,
    ROBUSTNESS_VARIANTS,
    STABLE,
    UNSTABLE,
    RobustnessVariant,
    summarize_robustness,
    variant_config,
)
from lab.session_runner import LabSessionRunner
from lab.walk_forward import window_metrics

REPO = Path(__file__).resolve().parents[2]
ENGINE_CONFIG = RiskConfig(stop_loss_required=False, version="risk-v1-nostop-mvp-a")


def test_variant_set_is_small_and_explicit() -> None:
    assert len(ROBUSTNESS_VARIANTS) == 7
    names = [variant.name for variant in ROBUSTNESS_VARIANTS]
    assert names[0] == "baseline"
    assert len(set(names)) == 7


def test_each_variant_differs_in_exactly_one_param() -> None:
    base = ROBUSTNESS_VARIANTS[0]
    assert (base.ema_fast, base.ema_slow, base.rsi_period, base.rsi_exit) == (20, 50, 14, 80.0)
    for variant in ROBUSTNESS_VARIANTS[1:]:
        diffs = sum(
            1
            for a, b in zip(
                (variant.ema_fast, variant.ema_slow, variant.rsi_period, variant.rsi_exit),
                (base.ema_fast, base.ema_slow, base.rsi_period, base.rsi_exit),
                strict=True,
            )
            if a != b
        )
        assert diffs == 1, variant.name


def test_variant_config_maps_exactly() -> None:
    config = variant_config(RobustnessVariant("x", 18, 45, 14, 75.0))
    assert isinstance(config, EmaRsiConfig)
    assert (config.ema_fast, config.ema_slow, config.rsi_period, config.rsi_exit) == (
        18,
        45,
        14,
        75.0,
    )


def test_summarize_stable_when_signs_agree() -> None:
    summary = summarize_robustness({"baseline": -1.5, "v1": -0.5, "v2": 0.0, "v3": -2.0})
    assert summary["stable"] == STABLE
    assert summary["baseline_net_pnl"] == -1.5
    assert summary["variants"] == 4
    assert summary["min_net_pnl"] == -2.0
    assert summary["max_net_pnl"] == 0.0
    assert summary["median_net_pnl"] == -1.0


def test_summarize_unstable_on_sign_flip() -> None:
    summary = summarize_robustness({"baseline": -1.5, "v1": 2.0})
    assert summary["stable"] == UNSTABLE


def test_summarize_inconclusive_on_flat_baseline() -> None:
    summary = summarize_robustness({"baseline": 0.0, "v1": 1.0})
    assert summary["stable"] == INCONCLUSIVE


def test_summarize_without_baseline_rejected() -> None:
    import pytest

    with pytest.raises(ValueError, match="baseline ausente"):
        summarize_robustness({"v1": 1.0})


def test_summarize_selects_no_winner() -> None:
    summary = summarize_robustness({"baseline": -1.0, "v1": -0.5})
    assert set(summary) == {
        "baseline_net_pnl",
        "variants",
        "min_net_pnl",
        "max_net_pnl",
        "median_net_pnl",
        "stable",
    }


def test_all_variants_run_on_development_slice() -> None:
    adapter = FrozenDatasetAdapter.from_repo(
        REPO, symbol="ETHUSDT", timeframe="15m", row_start=0, row_end=64
    )
    nets: dict[str, float] = {}
    for variant in ROBUSTNESS_VARIANTS:
        result = LabSessionRunner(
            adapter=adapter,
            strategy=EmaRsiBaseline(variant_config(variant)),
            engine=PaperEngine(config=ENGINE_CONFIG),
            experiment_spec_id="ab" * 32,
        ).run()
        nets[variant.name] = float(window_metrics(result)["net_pnl"])
    assert set(nets) == {variant.name for variant in ROBUSTNESS_VARIANTS}
    summary = summarize_robustness(nets)
    assert summary["stable"] in (STABLE, UNSTABLE, INCONCLUSIVE)

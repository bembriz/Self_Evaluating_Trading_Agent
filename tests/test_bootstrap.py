"""Tests de bootstrap y Monte Carlo sobre trades (PRD §47)."""

from __future__ import annotations

import pytest

from domain.evaluation.bootstrap import (
    ConfidenceInterval,
    bootstrap_ci,
    monte_carlo_drawdown,
    sharpe_of,
)


def _net_pnls() -> list[float]:
    # 60 trades con expectancia positiva y variación controlada.
    return [float((i % 7) - 2) * 10 + 5 for i in range(60)]


def test_bootstrap_ci_positive_expectancy() -> None:
    ci = bootstrap_ci(_net_pnls(), n_bootstraps=1000, seed=42)
    assert isinstance(ci, ConfidenceInterval)
    assert ci.point == pytest.approx(sum(_net_pnls()) / len(_net_pnls()))
    assert ci.low <= ci.point <= ci.high
    assert ci.n_samples == 60
    assert ci.method == "percentile-bootstrap"


def test_bootstrap_ci_deterministic_with_seed() -> None:
    a = bootstrap_ci(_net_pnls(), n_bootstraps=200, seed=7)
    b = bootstrap_ci(_net_pnls(), n_bootstraps=200, seed=7)
    assert (a.low, a.high) == (b.low, b.high)


def test_bootstrap_ci_empty_raises() -> None:
    with pytest.raises(ValueError, match="vacía"):
        bootstrap_ci([], seed=1)


def test_sharpe_known_series() -> None:
    rets2 = [0.01, -0.005] * 50
    rets2 = [0.01, -0.005] * 50
    s = sharpe_of(rets2)
    assert s is not None and s != 0.0
    assert sharpe_of([0.0]) is None  # sin desviación ni datos suficientes


def test_monte_carlo_drawdown_quantiles_and_ruin() -> None:
    report = monte_carlo_drawdown(
        net_pnls=_net_pnls(),
        initial_capital=1000.0,
        n_sims=500,
        seed=3,
        ruin_threshold=0.5,
    )
    assert report.p50_drawdown <= report.p95_drawdown <= report.p99_drawdown
    assert 0.0 <= report.ruin_probability <= 1.0
    assert report.n_sims == 500


def test_monte_carlo_ruin_certain_when_all_losses() -> None:
    report = monte_carlo_drawdown(
        net_pnls=[-600.0],
        initial_capital=1000.0,
        n_sims=50,
        seed=1,
        ruin_threshold=0.5,
    )
    assert report.ruin_probability == pytest.approx(1.0)


def test_monte_carlo_deterministic_with_seed() -> None:
    a = monte_carlo_drawdown(net_pnls=_net_pnls(), initial_capital=1000.0, n_sims=200, seed=9)
    b = monte_carlo_drawdown(net_pnls=_net_pnls(), initial_capital=1000.0, n_sims=200, seed=9)
    assert (a.p50_drawdown, a.p99_drawdown) == (b.p50_drawdown, b.p99_drawdown)

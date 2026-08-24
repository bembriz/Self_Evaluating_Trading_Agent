"""Tests de sensibilidades y análisis por regímenes (PRD §47)."""

import pytest

from domain.evaluation.sensitivity import (
    ParameterSensitivityReport,
    analyze_regimes,
    fee_sensitivity,
    parameter_sensitivity,
    slippage_sensitivity,
)
from domain.portfolio.portfolio import Trade


def _trade(
    net: float,
    qty: float = 0.5,
    entry: float = 2000.0,
    exit_: float | None = None,
    regime: str = "SIDEWAYS",
) -> Trade:
    return Trade(
        entry_ts=1000,
        exit_ts=2000,
        entry_price=entry,
        exit_price=exit_ if exit_ is not None else entry + net / qty,
        quantity=qty,
        gross_pnl=net + 2.0,
        fees=1.0,
        slippage=1.0,
        net_pnl=net,
    )


def test_fee_sensitivity_monotonic_degradation() -> None:
    trades = [_trade(10.0), _trade(-3.0)]
    points = fee_sensitivity(trades, bps_range=(10.0, 20.0, 40.0))
    nets = [p.total_net_pnl for p in points]
    assert len(points) == 3
    assert all(a >= b for a, b in zip(nets, nets[1:], strict=False))  # más fees ⇒ menos PnL
    assert points[1].extra_cost_usd > 0


def test_fee_sensitivity_survival_flag() -> None:
    trades = [_trade(20.0)]  # margen amplio para soportar el extremo
    points = fee_sensitivity(trades, bps_range=(10.0, 500.0))
    assert points[0].survives is True
    assert points[-1].survives is False


def test_slippage_sensitivity_symmetric_to_fees() -> None:
    trades = [_trade(8.0)]
    pts = slippage_sensitivity(trades, bps_range=(2.0, 12.0))
    assert pts[0].total_net_pnl > pts[-1].total_net_pnl


def test_parameter_sensitivity_detects_narrow_peak() -> None:
    grid = {
        (5, 10): -5.0,
        (5, 20): -4.0,
        (10, 10): -3.0,
        (10, 20): 50.0,  # único punto rentable
        (15, 10): -2.0,
        (15, 20): -6.0,
    }
    report: ParameterSensitivityReport = parameter_sensitivity(grid)
    assert report.best_params == (10, 20)
    assert report.neighbor_profitable_ratio == pytest.approx(0.0)
    assert report.is_robust is False  # pico estrecho ⇒ rechazo automático


def test_parameter_sensitivity_profitable_neighborhood_is_robust() -> None:
    grid = {(i, j): float(10 + i + j) for i in range(3) for j in range(3)}
    report = parameter_sensitivity(grid)
    assert report.is_robust is True
    assert report.neighbor_profitable_ratio == pytest.approx(1.0)


def test_regime_analysis_requires_two_profitable() -> None:
    by_regime = [
        ("TREND_UP", [_trade(10.0), _trade(5.0)]),
        ("SIDEWAYS", [_trade(-2.0), _trade(1.0)]),
    ]
    report = analyze_regimes(by_regime)
    stats = {r.regime: r for r in report.per_regime}
    assert stats["TREND_UP"].profitable is True
    assert stats["SIDEWAYS"].profitable is False
    assert report.profitable_regimes == 1
    assert report.meets_two_regime_rule is False

    both = [("TREND_UP", [_trade(10.0)]), ("TREND_DOWN", [_trade(4.0)])]
    assert analyze_regimes(both).meets_two_regime_rule is True

import pytest

from domain.evaluation.metrics import compute_metrics
from domain.portfolio.portfolio import Trade


def _trade(gross: float, fees: float, slippage: float) -> Trade:
    return Trade(
        entry_ts=0,
        exit_ts=1,
        entry_price=100.0,
        exit_price=100.0 + gross,
        quantity=1.0,
        gross_pnl=gross,
        fees=fees,
        slippage=slippage,
        net_pnl=gross - fees,
    )


def test_no_trades() -> None:
    m = compute_metrics([], [100.0, 100.0], periods_per_year=8760)
    assert m.trades == 0
    assert m.gross_pnl == 0.0
    assert m.net_pnl == 0.0
    assert m.win_rate is None
    assert m.profit_factor is None
    assert m.expectancy is None


def test_net_pnl_subtracts_costs() -> None:
    trades = [_trade(10.0, 1.0, 0.5), _trade(-4.0, 1.0, 0.5)]
    m = compute_metrics(trades, [100.0], periods_per_year=8760)
    assert m.gross_pnl == pytest.approx(6.0)
    assert m.fees == pytest.approx(2.0)
    assert m.slippage == pytest.approx(1.0)
    assert m.net_pnl == pytest.approx(4.0)
    assert m.fully_loaded_pnl == pytest.approx(4.0)


def test_win_rate_and_loss_rate() -> None:
    trades = [_trade(5.0, 0, 0), _trade(3.0, 0, 0), _trade(-2.0, 0, 0)]
    m = compute_metrics(trades, [100.0], periods_per_year=8760)
    assert m.win_rate == pytest.approx(2 / 3)
    assert m.loss_rate == pytest.approx(1 / 3)


def test_profit_factor_inf_when_no_losses() -> None:
    m = compute_metrics([_trade(5.0, 0, 0)], [100.0], periods_per_year=8760)
    assert m.profit_factor == float("inf")


def test_profit_factor_ratio() -> None:
    trades = [_trade(10.0, 0, 0), _trade(5.0, 0, 0), _trade(-3.0, 0, 0)]
    m = compute_metrics(trades, [100.0], periods_per_year=8760)
    assert m.profit_factor == pytest.approx(15.0 / 3.0)


def test_constant_equity_has_no_sharpe() -> None:
    m = compute_metrics([], [100.0] * 10, periods_per_year=8760)
    assert m.sharpe is None
    assert m.sortino is None


def test_max_drawdown_fraction() -> None:
    equity = [100.0, 110.0, 90.0, 95.0]
    m = compute_metrics([], equity, periods_per_year=8760)
    assert m.max_drawdown == pytest.approx((110.0 - 90.0) / 110.0)


def test_expectancy_avg_winner_loser_risk_reward() -> None:
    trades = [_trade(10.0, 0, 0), _trade(6.0, 0, 0), _trade(-4.0, 0, 0)]
    m = compute_metrics(trades, [100.0], periods_per_year=8760)
    assert m.avg_winner == pytest.approx(8.0)
    assert m.avg_loser == pytest.approx(-4.0)
    assert m.risk_reward == pytest.approx(2.0)
    assert m.expectancy == pytest.approx(12.0 / 3.0)


def test_sharpe_positive_for_rising_equity() -> None:
    equity = [float(100 + i) for i in range(10)]
    m = compute_metrics([], equity, periods_per_year=8760)
    assert m.sharpe is not None
    assert m.sharpe > 0


def test_llm_cost_reduces_fully_loaded_only() -> None:
    trades = [_trade(10.0, 1.0, 0.5)]
    m = compute_metrics(trades, [100.0], periods_per_year=8760, llm_cost=2.0)
    assert m.net_pnl == pytest.approx(9.0)
    assert m.fully_loaded_pnl == pytest.approx(7.0)
    assert m.llm_cost == pytest.approx(2.0)


def test_exposure_and_holding_passthrough() -> None:
    m = compute_metrics([], [100.0], periods_per_year=8760, exposure=0.5, avg_holding_bars=10.0)
    assert m.exposure == pytest.approx(0.5)
    assert m.avg_holding_bars == pytest.approx(10.0)


def test_returns_skips_zero_prev() -> None:
    equity = [0.0, 10.0, 20.0]
    m = compute_metrics([], equity, periods_per_year=8760)
    assert m.max_drawdown == pytest.approx(0.0)


def test_max_drawdown_zero_for_nonpositive_equity() -> None:
    m = compute_metrics([], [-5.0, -3.0, -1.0], periods_per_year=8760)
    assert m.max_drawdown == 0.0

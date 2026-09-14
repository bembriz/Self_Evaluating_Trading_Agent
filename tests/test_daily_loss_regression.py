"""Permanent daily-loss regression tests — Phase 21R-B.

Proves independently that:
- loss reaches max_daily_loss → BUY rejected
- SELL remains permitted during daily loss
- HOLD remains permitted during daily loss
- UTC day transition resets daily realized PnL
- BUY becomes eligible next UTC day
- previous-day losses cannot block future days
- multi-day sequence cannot become permanently locked
"""

import pytest

from application.services.paper_engine import OutOfOrderTimestampError, PaperEngine
from domain.risk.config import RiskConfig
from domain.trading.decision import TradingDecision
from domain.trading.signal import Action, Intensity


def _make_engine(capital: float = 1000.0, max_daily_loss: float = 0.03) -> PaperEngine:
    return PaperEngine(
        config=RiskConfig(
            capital=capital,
            max_daily_loss=max_daily_loss,
            stop_loss_required=False,
        )
    )


def _buy_decision(ts: int, price: float = 100.0) -> TradingDecision:
    return TradingDecision(
        timestamp_ms=ts,
        action=Action.BUY,
        confidence=1.0,
        intensity=Intensity.MEDIUM,
        rationale_summary="test",
    )


def _sell_decision(ts: int, price: float = 100.0) -> TradingDecision:
    return TradingDecision(
        timestamp_ms=ts,
        action=Action.SELL,
        confidence=1.0,
        intensity=Intensity.MEDIUM,
        rationale_summary="test",
    )


def _hold_decision(ts: int) -> TradingDecision:
    return TradingDecision(
        timestamp_ms=ts,
        action=Action.HOLD,
        confidence=1.0,
        intensity=Intensity.LOW,
        rationale_summary="test",
    )


MS_PER_DAY = 86_400_000


# ---------------------------------------------------------------------------
# R1. loss reaches max_daily_loss
# ---------------------------------------------------------------------------


def test_loss_reaches_max_daily_loss() -> None:
    """When realized daily loss hits the limit, daily_loss_active becomes True."""
    engine = _make_engine(capital=1000.0, max_daily_loss=0.001)
    # Day 1: buy and sell at a loss (need > 0.1% loss of capital = 1.0 USDT)
    engine.on_price(
        decision=_buy_decision(1000),
        price=100.0,
        atr=None,
        timestamp_ms=1000,
    )
    # Sell at 1% loss to exceed 0.1% of capital
    engine.on_price(
        decision=_sell_decision(2000),
        price=95.0,
        atr=None,
        timestamp_ms=2000,
    )
    assert engine.daily_loss_active is True


# ---------------------------------------------------------------------------
# R2. new BUY rejected during same UTC day
# ---------------------------------------------------------------------------


def test_buy_rejected_during_same_utc_day() -> None:
    """After daily loss triggered, new BUY is rejected on same UTC day."""
    engine = _make_engine(capital=1000.0, max_daily_loss=0.001)
    engine.on_price(
        decision=_buy_decision(1000),
        price=100.0,
        atr=None,
        timestamp_ms=1000,
    )
    engine.on_price(
        decision=_sell_decision(2000),
        price=95.0,
        atr=None,
        timestamp_ms=2000,
    )
    assert engine.daily_loss_active is True

    # Try another BUY on same day
    event = engine.on_price(
        decision=_buy_decision(3000),
        price=100.0,
        atr=None,
        timestamp_ms=3000,
    )
    assert event.filled is False
    assert event.risk_reason == "max_daily_loss"


# ---------------------------------------------------------------------------
# R3. SELL remains permitted
# ---------------------------------------------------------------------------


def test_sell_permitted_during_daily_loss() -> None:
    """SELL is always permitted even when daily loss is active."""
    engine = _make_engine(capital=1000.0, max_daily_loss=0.001)
    engine.on_price(
        decision=_buy_decision(1000),
        price=100.0,
        atr=None,
        timestamp_ms=1000,
    )
    engine.on_price(
        decision=_sell_decision(2000),
        price=95.0,
        atr=None,
        timestamp_ms=2000,
    )
    assert engine.daily_loss_active is True

    # Open a new position and try to sell
    engine.on_price(
        decision=_buy_decision(3000),
        price=100.0,
        atr=None,
        timestamp_ms=3000,
    )
    # This will be rejected because daily_loss_active
    # But if we manually set position, SELL should work
    # Let's test via the risk engine directly
    from domain.risk.engine import PortfolioRiskState, RiskEngine, TradeProposal

    risk = RiskEngine(engine._config)
    proposal = TradeProposal(
        action=Action.SELL,
        intensity=Intensity.MEDIUM,
        price=100.0,
        atr=None,
        timestamp_ms=4000,
    )
    state = PortfolioRiskState(
        open_positions=1,
        realized_pnl_today=-30.0,  # well below limit
        peak_equity=1000.0,
        equity=970.0,
        kill_switch=engine._kill_switch.state,
    )
    verdict = risk.evaluate(proposal, state)
    assert verdict.approved is True
    assert verdict.reason == "reduce"


# ---------------------------------------------------------------------------
# R4. HOLD remains permitted
# ---------------------------------------------------------------------------


def test_hold_permitted_during_daily_loss() -> None:
    """HOLD is always permitted even when daily loss is active."""
    engine = _make_engine(capital=1000.0, max_daily_loss=0.001)
    engine.on_price(
        decision=_buy_decision(1000),
        price=100.0,
        atr=None,
        timestamp_ms=1000,
    )
    engine.on_price(
        decision=_sell_decision(2000),
        price=95.0,
        atr=None,
        timestamp_ms=2000,
    )
    assert engine.daily_loss_active is True

    event = engine.on_price(
        decision=_hold_decision(3000),
        price=100.0,
        atr=None,
        timestamp_ms=3000,
    )
    assert event.filled is False
    assert event.action is Action.HOLD


# ---------------------------------------------------------------------------
# R5. UTC day transition resets daily realized PnL
# ---------------------------------------------------------------------------


def test_utc_day_transition_resets_daily_pnl() -> None:
    """On UTC day change, realized_pnl_today resets to 0."""
    engine = _make_engine(capital=1000.0, max_daily_loss=0.001)
    # Day 1
    day1_start = MS_PER_DAY * 1000  # some day
    engine.on_price(
        decision=_buy_decision(day1_start + 1000),
        price=100.0,
        atr=None,
        timestamp_ms=day1_start + 1000,
    )
    engine.on_price(
        decision=_sell_decision(day1_start + 2000),
        price=95.0,
        atr=None,
        timestamp_ms=day1_start + 2000,
    )
    assert engine.realized_pnl_today != 0.0

    # Day 2: transition
    day2_start = day1_start + MS_PER_DAY
    engine.on_price(
        decision=_hold_decision(day2_start + 1000),
        price=100.0,
        atr=None,
        timestamp_ms=day2_start + 1000,
    )
    assert engine.realized_pnl_today == 0.0


# ---------------------------------------------------------------------------
# R6. BUY becomes eligible next UTC day
# ---------------------------------------------------------------------------


def test_buy_eligible_next_utc_day() -> None:
    """After UTC day reset, BUY is no longer blocked by daily loss."""
    engine = _make_engine(capital=1000.0, max_daily_loss=0.001)
    day1_start = MS_PER_DAY * 1000

    # Day 1: trigger daily loss
    engine.on_price(
        decision=_buy_decision(day1_start + 1000),
        price=100.0,
        atr=None,
        timestamp_ms=day1_start + 1000,
    )
    engine.on_price(
        decision=_sell_decision(day1_start + 2000),
        price=95.0,
        atr=None,
        timestamp_ms=day1_start + 2000,
    )
    assert engine.daily_loss_active is True

    # Day 2: BUY should be allowed again
    day2_start = day1_start + MS_PER_DAY
    event = engine.on_price(
        decision=_buy_decision(day2_start + 1000),
        price=100.0,
        atr=None,
        timestamp_ms=day2_start + 1000,
    )
    assert event.filled is True
    assert event.action is Action.BUY


# ---------------------------------------------------------------------------
# R7. previous-day losses cannot block future days
# ---------------------------------------------------------------------------


def test_previous_day_losses_cannot_block_future() -> None:
    """Losses from day N do not affect day N+1's daily loss budget."""
    engine = _make_engine(capital=1000.0, max_daily_loss=0.001)
    day1 = MS_PER_DAY * 1000
    day2 = day1 + MS_PER_DAY

    # Day 1: large loss
    engine.on_price(
        decision=_buy_decision(day1 + 1000),
        price=100.0,
        atr=None,
        timestamp_ms=day1 + 1000,
    )
    engine.on_price(
        decision=_sell_decision(day1 + 2000),
        price=95.0,
        atr=None,
        timestamp_ms=day1 + 2000,
    )

    # Day 2: daily loss is reset, BUY should work
    event = engine.on_price(
        decision=_buy_decision(day2 + 1000),
        price=100.0,
        atr=None,
        timestamp_ms=day2 + 1000,
    )
    assert event.filled is True


# ---------------------------------------------------------------------------
# R8. multi-day sequence cannot become permanently locked
# ---------------------------------------------------------------------------


def test_multi_day_sequence_not_permanently_locked() -> None:
    """Even with losses every day, each new day allows fresh BUY."""
    engine = _make_engine(capital=1000.0, max_daily_loss=0.001)

    for day_offset in range(5):
        day_start = MS_PER_DAY * (1000 + day_offset)
        # Buy
        engine.on_price(
            decision=_buy_decision(day_start + 1000),
            price=100.0,
            atr=None,
            timestamp_ms=day_start + 1000,
        )
        # Sell at loss
        engine.on_price(
            decision=_sell_decision(day_start + 2000),
            price=95.0,
            atr=None,
            timestamp_ms=day_start + 2000,
        )
        assert engine.daily_loss_active is True

        # Next day should reset
        next_day = day_start + MS_PER_DAY
        event = engine.on_price(
            decision=_buy_decision(next_day + 1000),
            price=100.0,
            atr=None,
            timestamp_ms=next_day + 1000,
        )
        assert event.filled is True, f"Day {day_offset + 2}: BUY should be allowed"


# ---------------------------------------------------------------------------
# OutOfOrderTimestampError
# ---------------------------------------------------------------------------


def test_out_of_order_timestamp_raises() -> None:
    """Out-of-order timestamps raise OutOfOrderTimestampError."""
    engine = _make_engine()
    engine.on_price(
        decision=_hold_decision(2000),
        price=100.0,
        atr=None,
        timestamp_ms=2000,
    )
    with pytest.raises(OutOfOrderTimestampError):
        engine.on_price(
            decision=_hold_decision(1000),
            price=100.0,
            atr=None,
            timestamp_ms=1000,
        )

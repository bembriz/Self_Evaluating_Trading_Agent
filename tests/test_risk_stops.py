"""Tests de stops ATR, take profit y trailing stop (PRD §23)."""

import pytest

from domain.risk.config import RiskConfig
from domain.risk.stops import initial_stop, take_profit, update_trailing


@pytest.fixture
def cfg() -> RiskConfig:
    return RiskConfig()


def test_initial_stop_below_entry_for_long(cfg: RiskConfig) -> None:
    stop = initial_stop(entry_price=2000.0, atr=10.0, config=cfg)
    assert stop == pytest.approx(2000.0 - 2.0 * 10.0)


def test_take_profit_is_r_multiple(cfg: RiskConfig) -> None:
    entry, stop = 2000.0, 1980.0
    tp = take_profit(entry_price=entry, stop_loss=stop, config=cfg)
    assert tp == pytest.approx(entry + cfg.take_profit_r_multiple * (entry - stop))
    assert tp == pytest.approx(2040.0)


def test_trailing_never_moves_down(cfg: RiskConfig) -> None:
    current = 1990.0
    # Precio máximo menor que el implícito en el stop actual ⇒ no retrocede.
    updated = update_trailing(current_stop=current, highest_price=2000.0, atr=10.0, config=cfg)
    assert updated == pytest.approx(current)


def test_trailing_rises_with_new_highs(cfg: RiskConfig) -> None:
    updated = update_trailing(current_stop=1980.0, highest_price=2100.0, atr=10.0, config=cfg)
    assert updated == pytest.approx(2100.0 - 3.0 * 10.0)
    assert updated > 1980.0


def test_trailing_monotonic_across_sequence(cfg: RiskConfig) -> None:
    stops: list[float] = [initial_stop(entry_price=2000.0, atr=10.0, config=cfg)]
    for high in (2010.0, 2050.0, 2030.0, 2080.0):
        stops.append(
            update_trailing(current_stop=stops[-1], highest_price=high, atr=10.0, config=cfg)
        )
    assert all(b >= a for a, b in zip(stops, stops[1:], strict=False))


def test_zero_atr_keeps_current_stop(cfg: RiskConfig) -> None:
    updated = update_trailing(current_stop=1980.0, highest_price=2100.0, atr=0.0, config=cfg)
    assert updated == pytest.approx(1980.0)

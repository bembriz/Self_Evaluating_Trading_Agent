"""Evaluador de outcomes de trades cerrados (PRD §46, Fase 11). Dominio puro.

MFE/MAE miden la excursión máxima favorable/adversa desde la entrada durante la
vida del trade; `result` clasifica por PnL neto (fees y slippage incluidos).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domain.portfolio.portfolio import Trade


class TradeResult(StrEnum):
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"


@dataclass(frozen=True, slots=True)
class TradeOutcome:
    """Resultado evaluado de un trade cerrado."""

    trade: Trade
    result: TradeResult
    mfe: float  # Maximum Favorable Excursion (precio, ≥ 0)
    mae: float  # Maximum Adverse Excursion (precio, ≥ 0)
    r_multiple: float | None  # net_pnl / riesgo inicial, si hay stop conocido


def evaluate_outcome(
    *,
    trade: Trade,
    highest_prices: list[float],
    lowest_prices: list[float],
    initial_stop: float | None = None,
) -> TradeOutcome:
    """Evalúa un trade cerrado a partir de su camino de precios."""
    entry = trade.entry_price
    mfe = max((max(highest_prices) if highest_prices else entry) - entry, 0.0)
    adverse = entry - (min(lowest_prices) if lowest_prices else entry)
    mae = max(adverse, 0.0)

    if trade.net_pnl > 0.0:
        result: TradeResult = TradeResult.WIN
    elif trade.net_pnl < 0.0:
        result = TradeResult.LOSS
    else:
        result = TradeResult.BREAKEVEN

    r_multiple: float | None = None
    if initial_stop is not None:
        risk = entry - initial_stop
        if risk > 0.0:
            r_multiple = trade.net_pnl / risk

    return TradeOutcome(trade=trade, result=result, mfe=mfe, mae=mae, r_multiple=r_multiple)

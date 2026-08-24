"""Simulación de fills (PRD §25): precio de ejecución + fees + slippage. Dominio puro."""

from __future__ import annotations

from dataclasses import dataclass

from domain.trading.fees import FeeModel
from domain.trading.signal import Action
from domain.trading.slippage import SlippageModel


@dataclass(frozen=True, slots=True)
class Fill:
    timestamp_ms: int
    action: Action
    price: float
    exec_price: float
    quantity: float
    notional: float
    fee: float
    slippage_cost: float


class FillModel:
    """Determina precio de ejecución (slippage) y costes para una orden de mercado."""

    def __init__(
        self, fee_model: FeeModel | None = None, slippage_model: SlippageModel | None = None
    ) -> None:
        self._fees = fee_model or FeeModel()
        self._slippage = slippage_model or SlippageModel()

    def buy(self, timestamp_ms: int, price: float, cash: float) -> Fill:
        if cash <= 0:
            return self._empty(timestamp_ms, Action.BUY, price)
        exec_price = price * (1.0 + self._slippage.rate)
        fee_rate = self._fees.taker_rate
        max_notional = cash / (1.0 + fee_rate)
        quantity = max_notional / exec_price
        notional = quantity * exec_price
        return Fill(
            timestamp_ms=timestamp_ms,
            action=Action.BUY,
            price=price,
            exec_price=exec_price,
            quantity=quantity,
            notional=notional,
            fee=notional * fee_rate,
            slippage_cost=quantity * (exec_price - price),
        )

    def sell(self, timestamp_ms: int, price: float, quantity: float) -> Fill:
        if quantity <= 0:
            return self._empty(timestamp_ms, Action.SELL, price)
        exec_price = price * (1.0 - self._slippage.rate)
        notional = quantity * exec_price
        return Fill(
            timestamp_ms=timestamp_ms,
            action=Action.SELL,
            price=price,
            exec_price=exec_price,
            quantity=quantity,
            notional=notional,
            fee=notional * self._fees.taker_rate,
            slippage_cost=quantity * (price - exec_price),
        )

    @staticmethod
    def _empty(timestamp_ms: int, action: Action, price: float) -> Fill:
        return Fill(
            timestamp_ms=timestamp_ms,
            action=action,
            price=price,
            exec_price=price,
            quantity=0.0,
            notional=0.0,
            fee=0.0,
            slippage_cost=0.0,
        )

"""Contabilidad de portfolio exacta (PRD §5, §25). Dominio puro.

Long-only spot: BUY solo con cash disponible (nunca cash negativo); SELL solo reduce
posición existente (nunca short). PnL neto = gross - fees - slippage.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.trading.fill import Fill


@dataclass(frozen=True, slots=True)
class Trade:
    entry_ts: int
    exit_ts: int
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    fees: float
    slippage: float
    net_pnl: float


@dataclass
class Portfolio:
    initial_cash: float
    cash: float
    position: float = 0.0
    avg_entry: float | None = None
    entry_ts: int | None = None
    realized_pnl: float = 0.0
    total_fees: float = 0.0
    total_slippage: float = 0.0
    entry_fees: float = 0.0
    entry_slippage: float = 0.0
    trades: list[Trade] = field(default_factory=list)

    def apply_buy(self, fill: Fill) -> None:
        if fill.quantity <= 0:
            return
        total_cost = fill.notional + fill.fee
        if total_cost > self.cash + 1e-9:
            raise ValueError("buy excede el cash disponible")
        if self.position == 0.0:
            self.avg_entry = fill.exec_price
            self.entry_ts = fill.timestamp_ms
        else:
            old_entry = self.avg_entry or 0.0
            self.avg_entry = (old_entry * self.position + fill.exec_price * fill.quantity) / (
                self.position + fill.quantity
            )
        self.position += fill.quantity
        self.cash -= total_cost
        self.entry_fees += fill.fee
        self.entry_slippage += fill.slippage_cost
        self.total_fees += fill.fee
        self.total_slippage += fill.slippage_cost

    def apply_sell(self, fill: Fill) -> None:
        if fill.quantity <= 0 or self.position <= 0:
            return
        quantity = min(fill.quantity, self.position)
        fraction = quantity / self.position
        allocated_entry_fees = self.entry_fees * fraction
        allocated_entry_slippage = self.entry_slippage * fraction
        scale = quantity / fill.quantity if fill.quantity > 0 else 0.0
        exit_fee = fill.fee * scale
        exit_slippage = fill.slippage_cost * scale
        exit_price = fill.exec_price
        gross_pnl = (exit_price - (self.avg_entry or 0.0)) * quantity
        fees = allocated_entry_fees + exit_fee
        slippage = allocated_entry_slippage + exit_slippage
        net_pnl = gross_pnl - fees - slippage

        self.cash += fill.notional * scale - exit_fee
        self.position -= quantity
        self.entry_fees -= allocated_entry_fees
        self.entry_slippage -= allocated_entry_slippage
        self.realized_pnl += net_pnl
        self.total_fees += exit_fee
        self.total_slippage += exit_slippage
        self.trades.append(
            Trade(
                entry_ts=self.entry_ts or 0,
                exit_ts=fill.timestamp_ms,
                entry_price=self.avg_entry or 0.0,
                exit_price=exit_price,
                quantity=quantity,
                gross_pnl=gross_pnl,
                fees=fees,
                slippage=slippage,
                net_pnl=net_pnl,
            )
        )
        if self.position <= 1e-12:
            self.position = 0.0
            self.avg_entry = None
            self.entry_ts = None

    def equity(self, price: float) -> float:
        return self.cash + self.position * price

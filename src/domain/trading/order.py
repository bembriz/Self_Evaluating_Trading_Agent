"""Órdenes del agente (Fase 12): solicitud, seguimiento y estados. Dominio puro.

`order_link_id` propio garantiza idempotencia y reconciliación con Bybit
(skill bybit-integration): cada orden lleva una clave generada localmente.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from enum import StrEnum


class OrderStatus(StrEnum):
    NEW = "New"
    PARTIALLY_FILLED = "PartiallyFilled"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"

    @staticmethod
    def terminal_states() -> frozenset[OrderStatus]:
        return frozenset({OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED})


@dataclass(frozen=True, slots=True)
class OrderRequest:
    """Solicitud de orden spot (long-only: side Buy/Sell para cerrar)."""

    symbol: str
    side: str  # "Buy" | "Sell"
    quantity: float
    order_type: str = "Market"  # Market | Limit
    price: float | None = None
    order_link_id: str = field(default_factory=lambda: f"seta-{uuid.uuid4().hex[:15]}")


@dataclass(slots=True)
class TrackedOrder:
    """Estado local de una orden enviada al exchange."""

    order_link_id: str
    symbol: str
    status: OrderStatus
    cumulative_qty: float = 0.0
    avg_price: float | None = None
    exchange_order_id: str = ""

    def update(
        self, *, status: OrderStatus, cumulative_qty: float, avg_price: float | None = None
    ) -> None:
        if self.is_terminal():
            raise ValueError("orden terminal: no admite transiciones")
        self.status = status
        self.cumulative_qty = max(self.cumulative_qty, cumulative_qty)
        if avg_price is not None:
            self.avg_price = avg_price

    def is_terminal(self) -> bool:
        return self.status in OrderStatus.terminal_states()

    def as_open_state(self) -> dict[str, str]:
        return {"orderLinkId": self.order_link_id, "status": self.status.value}


def replace_status(order: TrackedOrder, status: OrderStatus) -> TrackedOrder:
    """Variante inmutable (útil en tests/reconciliación pura)."""
    return replace(order, status=status)

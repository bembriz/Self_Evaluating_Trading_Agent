"""Puerto de persistencia de features de order book (Protocol)."""

from __future__ import annotations

from typing import Protocol

from domain.market.features import OrderBookFeatureSnapshot


class OrderBookFeatureRepository(Protocol):
    async def insert(self, feature: OrderBookFeatureSnapshot) -> None: ...

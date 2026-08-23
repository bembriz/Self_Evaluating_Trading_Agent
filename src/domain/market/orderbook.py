"""Order book local y estado de salud del mercado (PRD §14). Sin frameworks."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum


class MarketDataHealth(StrEnum):
    HEALTHY = "healthy"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    price: float
    size: float


class OrderBookDesync(Exception):
    """Se perdió la secuencia de deltas: el book puede estar corrupto."""


@dataclass
class OrderBook:
    symbol: str
    bids: dict[float, float] = field(default_factory=dict)
    asks: dict[float, float] = field(default_factory=dict)
    update_id: int | None = None

    def apply_snapshot(
        self,
        bids: Sequence[OrderBookLevel],
        asks: Sequence[OrderBookLevel],
        update_id: int,
    ) -> None:
        self.bids = {lvl.price: lvl.size for lvl in bids if lvl.size > 0}
        self.asks = {lvl.price: lvl.size for lvl in asks if lvl.size > 0}
        self.update_id = update_id

    def apply_delta(
        self,
        bids: Sequence[OrderBookLevel],
        asks: Sequence[OrderBookLevel],
        update_id: int,
    ) -> None:
        if self.update_id is not None and update_id > self.update_id + 1:
            raise OrderBookDesync(
                f"gap en secuencia: esperado {self.update_id + 1}, recibido {update_id}"
            )
        if self.update_id is not None and update_id <= self.update_id:
            return
        self._apply_levels(self.bids, bids)
        self._apply_levels(self.asks, asks)
        self.update_id = update_id

    @staticmethod
    def _apply_levels(book: dict[float, float], levels: Sequence[OrderBookLevel]) -> None:
        for lvl in levels:
            if lvl.size == 0:
                book.pop(lvl.price, None)
            else:
                book[lvl.price] = lvl.size

    @property
    def best_bid(self) -> float | None:
        return max(self.bids) if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return min(self.asks) if self.asks else None

    @property
    def mid(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    @property
    def spread_pct(self) -> float | None:
        if self.mid is None or self.spread is None or self.mid == 0:
            return None
        return self.spread / self.mid

    def depth(self, side: str, levels: int) -> float:
        book = self.bids if side == "bids" else self.asks
        prices = sorted(book, reverse=(side == "bids"))[:levels]
        return sum(book[p] for p in prices)

    @property
    def imbalance(self) -> float | None:
        bid_depth = self.depth("bids", 50)
        ask_depth = self.depth("asks", 50)
        total = bid_depth + ask_depth
        if total == 0:
            return None
        return bid_depth / total

    @property
    def is_healthy(self) -> bool:
        return self.best_bid is not None and self.best_ask is not None

"""Puerto del stream de market data en tiempo real (Protocol)."""

from __future__ import annotations

from typing import Protocol

from domain.market.candle import Timeframe
from domain.market.stream import KlineUpdate, OrderBookDelta, OrderBookSnapshot

StreamEvent = OrderBookSnapshot | OrderBookDelta | KlineUpdate


class WebSocketDisconnected(Exception):
    """La conexión WebSocket se perdió y debe reconectarse."""


class MarketDataStream(Protocol):
    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    async def subscribe_orderbook(self, symbol: str, depth: int) -> None: ...

    async def subscribe_kline(self, symbol: str, interval: Timeframe) -> None: ...

    async def recv(self) -> StreamEvent:
        """Bloquea hasta el siguiente evento; lanza WebSocketDisconnected al caer."""
        ...

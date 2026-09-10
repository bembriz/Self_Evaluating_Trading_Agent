"""Cliente WebSocket público de Bybit v5 (PRD §13–14; skill bybit-integration)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, cast

from websockets.asyncio.client import connect as _connect
from websockets.exceptions import ConnectionClosed

from application.ports.market_stream import StreamEvent, WebSocketDisconnected
from domain.market.candle import Timeframe
from domain.market.orderbook import OrderBookLevel
from domain.market.stream import KlineUpdate, OrderBookDelta, OrderBookSnapshot
from infrastructure.bybit.ws_schemas import (
    WsKlineMessage,
    WsOrderbookMessage,
)

DEFAULT_URL = "wss://stream.bybit.com/v5/public/spot"

#: Fábrica de conexión inyectable en tests: recibe la URL y devuelve un
#: async context manager que expone `send` y `recv`.
ConnectFn = Callable[[str], Any]


class BybitWebSocketClient:
    def __init__(self, url: str = DEFAULT_URL, connect: ConnectFn | None = None) -> None:
        self._url = url
        self._connect: ConnectFn = connect or _connect
        self._cm: Any = None
        self._ws: Any = None

    async def connect(self) -> None:
        self._cm = self._connect(self._url)
        try:
            self._ws = await self._cm.__aenter__()
        except BaseException:
            # La conexión nunca se estableció: descartar el context manager para
            # que close() no invoque __aexit__ sobre un `connect` sin `connection`
            # (websockets 17 lanza AttributeError en ese caso y enmascara el error
            # primario de red).
            self._cm = None
            raise

    async def close(self) -> None:
        cm, self._cm, self._ws = self._cm, None, None
        if cm is not None:
            await cm.__aexit__(None, None, None)

    async def subscribe_orderbook(self, symbol: str, depth: int) -> None:
        await self._send({"op": "subscribe", "args": [f"orderbook.{depth}.{symbol}"]})

    async def subscribe_kline(self, symbol: str, interval: Timeframe) -> None:
        await self._send({"op": "subscribe", "args": [f"kline.{interval.value}.{symbol}"]})

    async def _send(self, message: dict[str, Any]) -> None:
        if self._ws is None:
            raise WebSocketDisconnected("no conectado")
        await self._ws.send(json.dumps(message))

    async def recv(self) -> StreamEvent:
        while True:
            raw = await self._recv_raw()
            data = json.loads(raw)
            op = data.get("op")
            if op == "ping":
                await self._send({"op": "pong"})
                continue
            if op == "subscribe" or op == "pong":
                continue
            return self._parse(data)

    async def _recv_raw(self) -> str:
        if self._ws is None:
            raise WebSocketDisconnected("no conectado")
        try:
            return cast(str, await self._ws.recv())
        except ConnectionClosed as exc:
            raise WebSocketDisconnected(str(exc)) from exc

    def _parse(self, data: dict[str, Any]) -> StreamEvent:
        topic = str(data["topic"])
        if topic.startswith("orderbook"):
            return self._parse_orderbook(topic, data)
        if topic.startswith("kline"):
            return self._parse_kline(topic, data)
        raise WebSocketDisconnected(f"topic desconocido: {topic}")

    @staticmethod
    def _symbol_from_topic(topic: str) -> str:
        return topic.split(".")[2]

    def _parse_orderbook(self, topic: str, data: dict[str, Any]) -> StreamEvent:
        message = WsOrderbookMessage.model_validate(data)
        symbol = message.data.s
        bids = tuple(OrderBookLevel(price=float(p), size=float(s)) for p, s in message.data.b)
        asks = tuple(OrderBookLevel(price=float(p), size=float(s)) for p, s in message.data.a)
        if message.type == "snapshot":
            return OrderBookSnapshot(
                symbol=symbol,
                bids=bids,
                asks=asks,
                update_id=message.data.u,
                seq=message.data.seq,
            )
        return OrderBookDelta(
            symbol=symbol,
            bids=bids,
            asks=asks,
            update_id=message.data.u,
            seq=message.data.seq,
        )

    def _parse_kline(self, topic: str, data: dict[str, Any]) -> StreamEvent:
        message = WsKlineMessage.model_validate(data)
        symbol = self._symbol_from_topic(topic)
        item = message.data[0]
        interval = Timeframe(item.interval)
        return KlineUpdate(
            symbol=symbol,
            interval=interval,
            start_ms=item.start,
            open=float(item.open),
            high=float(item.high),
            low=float(item.low),
            close=float(item.close),
            volume=float(item.volume),
            turnover=float(item.turnover),
            confirm=item.confirm,
        )

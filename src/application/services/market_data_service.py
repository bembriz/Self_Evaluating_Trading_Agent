"""Orquestación del market data en tiempo real (PRD §13–14, §63 Market Worker)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from application.ports.market_repositories import MarketCandleRepository
from application.ports.market_stream import (
    MarketDataStream,
    StreamEvent,
    WebSocketDisconnected,
)
from application.ports.orderbook_features import OrderBookFeatureRepository
from domain.market.candle import Candle, Timeframe
from domain.market.features import OrderBookFeatureSnapshot
from domain.market.orderbook import MarketDataHealth, OrderBook, OrderBookDesync
from domain.market.stream import KlineUpdate, OrderBookDelta, OrderBookSnapshot


@dataclass(frozen=True, slots=True)
class MarketDataConfig:
    stale_timeout_seconds: float = 10.0
    feature_window_seconds: int = 5
    depth: int = 50


class MarketDataService:
    def __init__(
        self,
        stream: MarketDataStream,
        candle_repo: MarketCandleRepository,
        feature_repo: OrderBookFeatureRepository,
        config: MarketDataConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
        commit: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._stream = stream
        self._candle_repo = candle_repo
        self._feature_repo = feature_repo
        self._config = config or MarketDataConfig()
        self._clock = clock
        self._commit = commit
        self._books: dict[str, OrderBook] = {}
        self._health = MarketDataHealth.STALE
        self._last_message_at: float | None = None

    @property
    def health(self) -> MarketDataHealth:
        return self._health

    def check_stale(self) -> None:
        self._refresh_health()

    def _refresh_health(self) -> None:
        if (
            self._last_message_at is None
            or self._clock() - self._last_message_at > self._config.stale_timeout_seconds
        ):
            self._health = MarketDataHealth.STALE
        elif self._books and all(b.is_healthy for b in self._books.values()):
            self._health = MarketDataHealth.HEALTHY
        else:
            self._health = MarketDataHealth.STALE

    async def handle_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        book = self._books.setdefault(snapshot.symbol, OrderBook(snapshot.symbol))
        book.apply_snapshot(snapshot.bids, snapshot.asks, snapshot.update_id)
        self._last_message_at = self._clock()
        self._refresh_health()

    async def handle_delta(self, delta: OrderBookDelta) -> bool:
        """Aplica un delta; devuelve True si se debe resubscribir (gap)."""
        self._last_message_at = self._clock()
        book = self._books.get(delta.symbol)
        if book is None:
            self._health = MarketDataHealth.STALE
            return True
        try:
            book.apply_delta(delta.bids, delta.asks, delta.update_id)
        except OrderBookDesync:
            self._health = MarketDataHealth.STALE
            return True
        self._refresh_health()
        return False

    async def handle_kline(self, kline: KlineUpdate) -> Candle | None:
        self._last_message_at = self._clock()
        candle = kline.to_candle()
        if candle is not None:
            await self._candle_repo.upsert(kline.symbol, kline.interval, [candle])
        return candle

    async def aggregate_features(
        self, window_start_ms: int, window_end_ms: int
    ) -> list[OrderBookFeatureSnapshot]:
        snapshots: list[OrderBookFeatureSnapshot] = []
        for symbol, book in self._books.items():
            if not book.is_healthy:
                continue
            snapshot = OrderBookFeatureSnapshot(
                symbol=symbol,
                window_start_ms=window_start_ms,
                window_end_ms=window_end_ms,
                best_bid=book.best_bid,
                best_ask=book.best_ask,
                spread=book.spread,
                spread_pct=book.spread_pct,
                bid_depth=book.depth("bids", self._config.depth),
                ask_depth=book.depth("asks", self._config.depth),
                imbalance=book.imbalance,
            )
            await self._feature_repo.insert(snapshot)
            snapshots.append(snapshot)
        return snapshots

    async def run(self, symbols: list[str], timeframes: list[Timeframe]) -> None:
        """Sesión de una conexión. Lanza WebSocketDisconnected al caer la conexión."""
        await self._stream.connect()
        try:
            for symbol in symbols:
                await self._stream.subscribe_orderbook(symbol, self._config.depth)
                for timeframe in timeframes:
                    await self._stream.subscribe_kline(symbol, timeframe)
            await self._consume_loop()
        finally:
            await self._stream.close()

    async def _consume_loop(self) -> None:
        loop = asyncio.get_running_loop()
        next_window = loop.time() + self._config.feature_window_seconds
        while True:
            try:
                event = await asyncio.wait_for(
                    self._stream.recv(), timeout=self._config.stale_timeout_seconds
                )
            except TimeoutError:
                self._health = MarketDataHealth.STALE
                continue
            except WebSocketDisconnected:
                raise
            self._last_message_at = loop.time()
            await self._handle_event(event)
            if loop.time() >= next_window:
                now_ms = int(loop.time() * 1000)
                window_ms = self._config.feature_window_seconds * 1000
                await self.aggregate_features(now_ms - window_ms, now_ms)
                await self._maybe_commit()
                next_window = loop.time() + self._config.feature_window_seconds
            self._refresh_health()

    async def _maybe_commit(self) -> None:
        if self._commit is not None:
            await self._commit()

    async def _handle_event(self, event: StreamEvent) -> None:
        if isinstance(event, OrderBookSnapshot):
            await self.handle_snapshot(event)
        elif isinstance(event, OrderBookDelta):
            resubscribe = await self.handle_delta(event)
            if resubscribe:
                await self._stream.subscribe_orderbook(event.symbol, self._config.depth)
        elif isinstance(event, KlineUpdate):
            await self.handle_kline(event)

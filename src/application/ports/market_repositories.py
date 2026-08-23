"""Puertos de persistencia de market data en PostgreSQL (Protocols)."""

from __future__ import annotations

from typing import Protocol

from domain.market.candle import Candle, Timeframe
from domain.market.dataset import DatasetManifest


class MarketCandleRepository(Protocol):
    async def upsert(self, symbol: str, timeframe: Timeframe, candles: list[Candle]) -> int:
        """Inserta ignorando conflictos; devuelve filas insertadas."""
        ...

    async def count(self, symbol: str, timeframe: Timeframe) -> int: ...

    async def range(
        self, symbol: str, timeframe: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        """Candles con timestamp_ms en [start_ms, end_ms], ascendente."""
        ...


class DatasetManifestRepository(Protocol):
    async def upsert(self, manifest: DatasetManifest) -> None: ...

    async def get(self, version: str) -> DatasetManifest | None: ...

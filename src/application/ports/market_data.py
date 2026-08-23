"""Puerto de acceso a datos de mercado (Protocol)."""

from __future__ import annotations

from typing import Protocol

from domain.market.candle import Candle, Timeframe


class MarketDataClient(Protocol):
    """Fuente de candles históricas. Implementado por Bybit (y fakes en tests)."""

    async def fetch_candles(
        self, symbol: str, interval: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        """Candles ordenadas ascendente, dentro de [start_ms, end_ms] (inclusive)."""
        ...

"""Backfill de velas confirmadas desde Bybit REST para el recovery del paper-runner."""

from __future__ import annotations

from dataclasses import dataclass

from application.ports.market_data import MarketDataClient
from application.ports.market_repositories import MarketCandleRepository
from application.services.paper_runner import PaperRunner
from domain.market.candle import Timeframe

_MS_PER_MINUTE = 60_000


@dataclass(frozen=True, slots=True)
class BackfillResult:
    recovered: int
    skipped_partial: int


def candle_close_ms(candle_ts_ms: int, timeframe: Timeframe) -> int:
    """Timestamp de cierre de una vela (open + intervalo)."""
    return candle_ts_ms + timeframe.minutes * _MS_PER_MINUTE


class BackfillService:
    """Recupera velas confirmadas faltantes entre lo persistido y un cutoff."""

    def __init__(
        self,
        client: MarketDataClient,
        candle_repo: MarketCandleRepository,
    ) -> None:
        self._client = client
        self._candle_repo = candle_repo

    async def backfill(
        self,
        *,
        session_id: str,
        symbol: str,
        timeframe: Timeframe,
        cutoff_ms: int,
        runner: PaperRunner,
    ) -> BackfillResult:
        """Procesa cronológicamente las velas cerradas faltantes hasta ``cutoff_ms``."""
        last = await self._candle_repo.last_persisted_ms(session_id, symbol, timeframe)
        start = last + timeframe.minutes * _MS_PER_MINUTE if last is not None else 0
        candles = await self._client.fetch_candles(symbol, timeframe, start, cutoff_ms)

        recovered = 0
        skipped_partial = 0
        for candle in candles:
            if candle_close_ms(candle.timestamp_ms, timeframe) > cutoff_ms:
                skipped_partial += 1
                continue
            await runner.handle_candle(symbol, timeframe, candle)
            recovered += 1
        return BackfillResult(recovered=recovered, skipped_partial=skipped_partial)

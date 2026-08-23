"""Adaptador REST histórico de Bybit (PRD §13, §40; skill bybit-integration)."""

from __future__ import annotations

import asyncio
import random

import httpx

from domain.market.candle import Candle, Timeframe
from infrastructure.bybit.schemas import KlineResponse

BASE_URL = "https://api.bybit.com"
KLINE_PATH = "/v5/market/kline"
MAX_LIMIT = 1000


class BybitError(Exception):
    """Error devuelto por la API de Bybit."""


def _parse_candle(row: list[str]) -> Candle:
    ts, o, h, lo, c, v, t = row
    return Candle(
        timestamp_ms=int(ts),
        open=float(o),
        high=float(h),
        low=float(lo),
        close=float(c),
        volume=float(v),
        turnover=float(t),
    )


class BybitRestClient:
    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        max_retries: int = 3,
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)
        self._max_retries = max_retries

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_candles(
        self, symbol: str, interval: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        candles: dict[int, Candle] = {}
        cursor = end_ms
        for _ in range(10_000):
            data = await self._get_kline(symbol, interval, start_ms, cursor)
            batch = [_parse_candle(r) for r in data.result.list]
            if not batch:
                break
            earliest = min(c.timestamp_ms for c in batch)
            for c in batch:
                if start_ms <= c.timestamp_ms <= end_ms:
                    candles[c.timestamp_ms] = c
            if earliest <= start_ms:
                break
            cursor = earliest - 1
        return sorted(candles.values(), key=lambda c: c.timestamp_ms)

    async def _get_kline(
        self, symbol: str, interval: Timeframe, start_ms: int, end_ms: int
    ) -> KlineResponse:
        params = {
            "category": "spot",
            "symbol": symbol,
            "interval": interval.value,
            "start": start_ms,
            "end": end_ms,
            "limit": MAX_LIMIT,
        }
        for attempt in range(self._max_retries + 1):
            response = await self._client.get(KLINE_PATH, params=params)
            if response.status_code == 429 or response.status_code >= 500:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 2**attempt
                delay += random.uniform(0, 0.5)
                if attempt < self._max_retries:
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
            response.raise_for_status()
            raw = response.json()
            if raw.get("retCode") != 0:
                raise BybitError(f"Bybit retCode={raw.get('retCode')}: {raw.get('retMsg')}")
            return KlineResponse.model_validate(raw)
        raise BybitError("agotados los reintentos")

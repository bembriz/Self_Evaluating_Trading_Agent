import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from domain.market.candle import Timeframe
from infrastructure.bybit.client import BybitError, BybitRestClient

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "bybit_kline_spot.json").read_text())

_MAX_TS = max(int(r[0]) for r in FIXTURE["result"]["list"])


def _empty_list() -> dict[str, Any]:
    return {**FIXTURE, "result": {**FIXTURE["result"], "list": []}}


def _paged_handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/v5/market/kline"
    end = int(request.url.params["end"])
    return httpx.Response(200, json=FIXTURE if end >= _MAX_TS else _empty_list())


@pytest.fixture
def client() -> BybitRestClient:
    return BybitRestClient(transport=httpx.MockTransport(_paged_handler))


async def test_fetch_parses_candles(client: BybitRestClient) -> None:
    candles = await client.fetch_candles("ETHUSDT", Timeframe.M15, 0, 2**62)
    assert len(candles) == len(FIXTURE["result"]["list"])
    assert candles == sorted(candles, key=lambda c: c.timestamp_ms)
    first = candles[0]
    assert first.high >= max(first.open, first.close)
    await client.close()


async def test_retcode_nonzero_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"retCode": 10001, "retMsg": "boom"})

    c = BybitRestClient(transport=httpx.MockTransport(handler))
    with pytest.raises(BybitError):
        await c.fetch_candles("ETHUSDT", Timeframe.M15, 0, 1)
    await c.close()


async def test_429_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        end = int(request.url.params["end"])
        return httpx.Response(200, json=FIXTURE if end >= _MAX_TS else _empty_list())

    c = BybitRestClient(transport=httpx.MockTransport(handler), max_retries=2)
    candles = await c.fetch_candles("ETHUSDT", Timeframe.M15, 0, 2**62)
    assert candles
    assert calls["n"] == 3
    await c.close()

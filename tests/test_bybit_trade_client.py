"""Tests del cliente de trading Bybit v5 (Testnet) con MockTransport."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from domain.trading.order import OrderRequest, OrderStatus
from infrastructure.bybit.auth import BybitSigner
from infrastructure.bybit.trade_client import (
    BybitTradeClient,
    BybitTradeError,
    RemoteOrder,
)


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> BybitTradeClient:
    return BybitTradeClient(
        signer=BybitSigner(api_key="K", api_secret="S"),
        base_url="https://api-testnet.bybit.com",
        transport=httpx.MockTransport(handler),
    )


def _ok(ret: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, json={"retCode": 0, "retMsg": "OK", "result": ret})


async def test_place_order_returns_ids_and_tracks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/order/create"
        assert request.headers["X-BAPI-API-KEY"] == "K"
        body = request.read().decode()
        assert '"category":"spot"' in body.replace(" ", "")
        return _ok({"orderId": "oid-1", "orderLinkId": "seta-abc"})

    client = _client(handler)
    req = OrderRequest(symbol="ETHUSDT", side="Buy", quantity=0.5, order_link_id="seta-abc")
    res = await client.place_order(req)
    assert res.exchange_order_id == "oid-1"
    assert res.order_link_id == "seta-abc"
    await client.close()


async def test_place_order_ret_code_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"retCode": 110007, "retMsg": "insufficient balance"})

    client = _client(handler)
    with pytest.raises(BybitTradeError, match="110007"):
        await client.place_order(OrderRequest(symbol="ETHUSDT", side="Buy", quantity=1.0))
    await client.close()


async def test_cancel_order_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok({"orderId": "oid-1"})

    client = _client(handler)
    ok = await client.cancel_order(symbol="ETHUSDT", order_link_id="seta-abc")
    assert ok is True
    await client.close()


async def test_cancel_unknown_order_is_idempotent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"retCode": 110001, "retMsg": "order not exists"})

    client = _client(handler)
    ok = await client.cancel_order(symbol="ETHUSDT", order_link_id="missing")
    assert ok is False  # ya no existe: tratado como idempotente, no error
    await client.close()


async def test_open_orders_parses_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "symbol=ETHUSDT" in str(request.url)
        return _ok(
            {
                "list": [
                    {
                        "orderLinkId": "seta-a",
                        "orderId": "o1",
                        "orderStatus": "New",
                        "cumExecQty": "0",
                        "avgPrice": "",
                    },
                    {
                        "orderLinkId": "seta-b",
                        "orderId": "o2",
                        "orderStatus": "PartiallyFilled",
                        "cumExecQty": "0.3",
                        "avgPrice": "2000.5",
                    },
                ]
            }
        )

    client = _client(handler)
    remote = await client.open_orders(symbol="ETHUSDT")
    assert len(remote) == 2
    assert remote[0].order_link_id == "seta-a"
    assert remote[0].status is OrderStatus.NEW
    assert remote[1].cumulative_qty == pytest.approx(0.3)
    await client.close()


async def test_http_429_retries_with_backoff_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return _ok({"list": []})

    client = _client(handler)
    remote = await client.open_orders(symbol="ETHUSDT")
    assert calls["n"] == 2 and remote == []
    await client.close()


async def test_http_500_exhausted_raises_trade_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = _client(handler)
    with pytest.raises(BybitTradeError):
        await client.open_orders(symbol="ETHUSDT")
    await client.close()


def test_remote_order_parsing_defaults() -> None:
    r = RemoteOrder.model_validate(
        {
            "orderLinkId": "seta-x",
            "orderId": "o9",
            "status": "Cancelled",
            "cumExecQty": "1.25",
            "avgPrice": "1999.99",
        }
    )
    assert r.status is OrderStatus.CANCELLED
    assert r.cumulative_qty == 1.25 and r.avg_price == 1999.99

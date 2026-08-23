import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from domain.market.candle import Timeframe
from domain.market.stream import KlineUpdate, OrderBookDelta, OrderBookSnapshot
from infrastructure.bybit.ws import BybitWebSocketClient

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / f"bybit_ws_{name}.json").read_text()))


class FakeWS:
    def __init__(self, messages: list[str]) -> None:
        self.messages = list(messages)
        self.sent: list[str] = []

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def recv(self) -> str:
        if not self.messages:
            raise ConnectionError("closed")
        return self.messages.pop(0)

    async def __aenter__(self) -> "FakeWS":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None


def fake_connect(ws: FakeWS) -> Callable[[str], FakeWS]:
    def connect(url: str) -> FakeWS:
        del url
        return ws

    return connect


async def test_snapshot_parsing() -> None:
    ws = FakeWS([json.dumps(_load("snapshot"))])
    client = BybitWebSocketClient(connect=fake_connect(ws))
    await client.connect()
    event = await client.recv()
    assert isinstance(event, OrderBookSnapshot)
    assert event.symbol == "ETHUSDT"
    assert event.bids and event.asks
    assert event.update_id > 0
    await client.close()


async def test_delta_parsing() -> None:
    ws = FakeWS([json.dumps(_load("delta"))])
    client = BybitWebSocketClient(connect=fake_connect(ws))
    await client.connect()
    event = await client.recv()
    assert isinstance(event, OrderBookDelta)
    assert event.symbol == "ETHUSDT"
    await client.close()


async def test_kline_parsing_unconfirmed() -> None:
    ws = FakeWS([json.dumps(_load("kline_unconfirmed"))])
    client = BybitWebSocketClient(connect=fake_connect(ws))
    await client.connect()
    event = await client.recv()
    assert isinstance(event, KlineUpdate)
    assert event.interval is Timeframe.M15
    assert event.confirm is False
    await client.close()


async def test_ping_triggers_pong_and_skips() -> None:
    ws = FakeWS([json.dumps({"op": "ping"}), json.dumps(_load("delta"))])
    client = BybitWebSocketClient(connect=fake_connect(ws))
    await client.connect()
    event = await client.recv()
    assert isinstance(event, OrderBookDelta)
    assert any("pong" in s for s in ws.sent)
    await client.close()


async def test_subscribe_sends_args() -> None:
    ws = FakeWS([])
    client = BybitWebSocketClient(connect=fake_connect(ws))
    await client.connect()
    await client.subscribe_orderbook("ETHUSDT", 50)
    await client.subscribe_kline("ETHUSDT", Timeframe.M15)
    sent = [json.loads(s) for s in ws.sent]
    assert sent[0]["args"] == ["orderbook.50.ETHUSDT"]
    assert sent[1]["args"] == ["kline.15.ETHUSDT"]
    await client.close()

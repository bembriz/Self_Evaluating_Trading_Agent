"""Tests del adaptador DeepSeek (infrastructure/llm/deepseek.py, PRD §17-20).

Usa `httpx.MockTransport` para simular la API chat-completions sin red.
Cubre: decisión válida parseada, JSON inválido -> HOLD, schema inválido -> HOLD,
HTTP 500 -> HOLD con error, y render determinista de mensajes.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

import httpx
import pytest

from domain.llm.prompt import Prompt
from domain.market.orderbook import MarketDataHealth
from domain.market.state import MarketState
from domain.memory.memory import TradingMemory
from domain.trading.decision import DecisionContext
from domain.trading.signal import Action
from infrastructure.llm.deepseek import (
    DeepSeekConfig,
    DeepSeekProvider,
    render_decision_messages,
)


def _state() -> MarketState:
    return MarketState(
        symbol="ETHUSDT",
        timestamp_ms=1000,
        health=MarketDataHealth.HEALTHY,
        regime=None,
        timeframes={},
        orderbook=None,
        btc=None,
    )


def _ctx() -> DecisionContext:
    return DecisionContext(
        symbol="ETHUSDT",
        timestamp_ms=1000,
        experiment_id="",
        prompt_version="v001",
        market_state_hash="ms",
    )


def _prompt() -> Prompt:
    return Prompt(kind="decision", version="v001", text="sistema")


def _json_response(
    content: str,
    model: str = "deepseek-v4-flash",
    pt: int = 10,
    ct: int = 5,
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": pt, "completion_tokens": ct},
        },
    )


def _provider(handler: Callable[[httpx.Request], httpx.Response]) -> DeepSeekProvider:
    cfg = DeepSeekConfig(api_key="test-key")
    return DeepSeekProvider(cfg, transport=httpx.MockTransport(handler))


async def test_valid_decision_parsed_and_recorded() -> None:
    content = '{"decision":"BUY","confidence":0.7,"intensity":"HIGH","rationale_summary":"m"}'

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(content)

    provider = _provider(handler)
    result = await provider.decide(_state(), [], _ctx(), _prompt())
    assert result.decision.action is Action.BUY
    assert result.decision.is_fallback is False
    assert result.call.provider == "deepseek"
    assert result.call.reported_model_version == "deepseek-v4-flash"
    assert result.call.cost_usd > 0.0
    assert result.call.error == ""


async def test_invalid_json_falls_back_to_hold() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response("esto no es json")

    provider = _provider(handler)
    result = await provider.decide(_state(), [], _ctx(), _prompt())
    assert result.decision.action is Action.HOLD
    assert result.decision.is_fallback is True
    assert result.decision.fallback_reason == "invalid_json"


async def test_schema_invalid_falls_back_to_hold() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response('{"decision":"BUY","confidence":9.9,"intensity":"HIGH"}')

    provider = _provider(handler)
    result = await provider.decide(_state(), [], _ctx(), _prompt())
    assert result.decision.action is Action.HOLD
    assert result.decision.is_fallback is True
    assert result.decision.fallback_reason == "invalid_schema"


async def test_http_error_falls_back_to_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    async def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    provider = _provider(handler)
    result = await provider.decide(_state(), [], _ctx(), _prompt())
    assert result.decision.action is Action.HOLD
    assert result.decision.is_fallback is True
    assert result.call.error != ""


async def test_network_error_falls_back_to_hold() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    provider = _provider(handler)
    result = await provider.decide(_state(), [], _ctx(), _prompt())
    assert result.decision.action is Action.HOLD
    assert result.decision.is_fallback is True
    assert result.call.error != ""


async def test_non_object_json_falls_back_to_hold() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response("123")

    provider = _provider(handler)
    result = await provider.decide(_state(), [], _ctx(), _prompt())
    assert result.decision.action is Action.HOLD
    assert result.decision.is_fallback is True
    assert result.decision.fallback_reason == "invalid_schema"


async def test_retries_on_5xx_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(500, text="boom")
        return _json_response('{"decision":"BUY","confidence":0.7,"intensity":"HIGH"}')

    async def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    cfg = DeepSeekConfig(api_key="test-key", max_retries=2)
    provider = DeepSeekProvider(cfg, transport=httpx.MockTransport(handler))
    result = await provider.decide(_state(), [], _ctx(), _prompt())
    assert result.decision.action is Action.BUY
    assert result.decision.is_fallback is False
    assert calls["n"] == 3


async def test_retries_exhausted_returns_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    async def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    cfg = DeepSeekConfig(api_key="test-key", max_retries=2)
    provider = DeepSeekProvider(cfg, transport=httpx.MockTransport(handler))
    result = await provider.decide(_state(), [], _ctx(), _prompt())
    assert result.decision.action is Action.HOLD
    assert result.decision.is_fallback is True
    assert result.call.error != ""
    assert calls["n"] == 3


async def test_non_retryable_4xx_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}
    sleeps = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, text="unauthorized")

    async def fake_sleep(seconds: float) -> None:
        sleeps["n"] += 1

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    cfg = DeepSeekConfig(api_key="test-key", max_retries=2)
    provider = DeepSeekProvider(cfg, transport=httpx.MockTransport(handler))
    result = await provider.decide(_state(), [], _ctx(), _prompt())
    assert result.decision.action is Action.HOLD
    assert result.decision.is_fallback is True
    assert result.call.error != ""
    assert calls["n"] == 1
    assert sleeps["n"] == 0


def test_render_decision_messages_deterministic() -> None:
    state = _state()
    memories = [
        TradingMemory(id="m1", text="recuerdo", outcome_timestamp_ms=5, embedding=(0.1, 0.2))
    ]
    prompt = _prompt()
    first = render_decision_messages(prompt, state, memories)
    second = render_decision_messages(prompt, state, memories)
    assert first == second
    assert first[0] == {"role": "system", "content": "sistema"}
    assert first[1]["role"] == "user"
    payload = json.loads(first[1]["content"])
    assert payload["market_state"]["symbol"] == "ETHUSDT"
    assert payload["memories"][0]["text"] == "recuerdo"


async def test_close_closes_client() -> None:
    provider = _provider(lambda request: _json_response("{}"))
    await provider.close()

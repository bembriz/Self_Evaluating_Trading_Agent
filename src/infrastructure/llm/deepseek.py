"""Adaptador de infraestructura del proveedor DeepSeek (PRD §17-20).

Habla con la API chat-completions (compatible OpenAI) de DeepSeek y devuelve una
`DecisionResult` validada. Nunca lanza ante fallos esperados: timeout, error
HTTP, JSON inválido, schema inválido o confianza fuera de rango se resuelven en
un HOLD de seguridad con `fallback_reason` y un `LLMCallRecord` con `error`.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from application.ports.llm import DecisionResult
from domain.llm.call import LLMCallRecord
from domain.llm.cost import compute_cost
from domain.llm.prompt import Prompt
from domain.market.state import MarketState
from domain.memory.memory import TradingMemory
from domain.trading.decision import DecisionContext, TradingDecision
from infrastructure.llm.schemas import DecisionResponse, DeepSeekChatResponse


@dataclass(frozen=True, slots=True)
class DeepSeekConfig:
    """Configuración inmutable del proveedor DeepSeek (precios USD/1M tokens)."""

    api_key: str
    model: str = "deepseek-v4-flash"
    base_url: str = "https://api.deepseek.com"
    timeout: float = 30.0
    temperature: float = 0.0
    price_input_mtok: float = 0.27
    price_output_mtok: float = 1.10
    max_retries: int = 2


def render_decision_messages(
    prompt: Prompt,
    market_state: MarketState,
    memories: Sequence[TradingMemory],
) -> list[dict[str, str]]:
    """Construye los mensajes `system`/`user` de forma pura y determinista."""
    payload = {
        "market_state": dataclasses.asdict(market_state),
        "memories": [dataclasses.asdict(m) for m in memories],
    }
    content = json.dumps(payload, sort_keys=True, default=str)
    return [
        {"role": "system", "content": prompt.text},
        {"role": "user", "content": content},
    ]


class DeepSeekProvider:
    """Adaptador HTTP del proveedor DeepSeek; implementa `LLMProvider`."""

    def __init__(
        self,
        config: DeepSeekConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        headers = {"Authorization": f"Bearer {config.api_key}"}
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout,
            transport=transport,
            headers=headers,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def decide(
        self,
        market_state: MarketState,
        memories: Sequence[TradingMemory],
        context: DecisionContext,
        prompt: Prompt,
    ) -> DecisionResult:
        timestamp_ms = time.time_ns() // 1_000_000
        messages = render_decision_messages(prompt, market_state, memories)
        request_json = json.dumps(messages, sort_keys=True)

        body = {
            "model": self._config.model,
            "messages": messages,
            "temperature": self._config.temperature,
            "stream": False,
        }

        start = time.monotonic()
        response: httpx.Response | None = None
        for attempt in range(self._config.max_retries + 1):
            try:
                response = await self._client.post("/chat/completions", json=body)
            except httpx.HTTPError as exc:
                return self._hold(
                    timestamp_ms,
                    self._latency_ms(start),
                    request_json,
                    prompt,
                    context,
                    reason="network_error",
                    response_text="",
                    error=str(exc),
                )

            if response.status_code < 200 or response.status_code >= 300:
                if self._is_retryable(response.status_code) and attempt < self._config.max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                return self._hold(
                    timestamp_ms,
                    self._latency_ms(start),
                    request_json,
                    prompt,
                    context,
                    reason="http_error",
                    response_text=response.text,
                    error=f"HTTP {response.status_code}",
                )
            break

        assert response is not None
        latency_ms = self._latency_ms(start)

        try:
            chat = DeepSeekChatResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            return self._hold(
                timestamp_ms,
                latency_ms,
                request_json,
                prompt,
                context,
                reason="invalid_json",
                response_text=response.text,
                error=str(exc),
            )

        if not chat.choices:
            return self._hold(
                timestamp_ms,
                latency_ms,
                request_json,
                prompt,
                context,
                reason="empty_choices",
                response_text="",
                error="sin choices en la respuesta",
            )

        content = chat.choices[0].message.content
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            return self._hold(
                timestamp_ms,
                latency_ms,
                request_json,
                prompt,
                context,
                reason="invalid_json",
                response_text=content,
                error=str(exc),
            )

        try:
            decision_response = DecisionResponse.model_validate(parsed)
        except ValidationError as exc:
            return self._hold(
                timestamp_ms,
                latency_ms,
                request_json,
                prompt,
                context,
                reason="invalid_schema",
                response_text=content,
                error=str(exc),
            )

        decision = decision_response.to_decision(timestamp_ms)
        cost_usd = compute_cost(
            chat.usage.prompt_tokens,
            chat.usage.completion_tokens,
            self._config.price_input_mtok,
            self._config.price_output_mtok,
        )
        call = self._record(
            timestamp_ms=timestamp_ms,
            latency_ms=latency_ms,
            request_json=request_json,
            response_text=content,
            reported_model=chat.model,
            prompt_hash=prompt.hash,
            market_state_hash=context.market_state_hash,
            input_tokens=chat.usage.prompt_tokens,
            output_tokens=chat.usage.completion_tokens,
            cost_usd=cost_usd,
            error="",
        )
        return DecisionResult(decision=decision, call=call)

    @staticmethod
    def _latency_ms(start: float) -> int:
        return int((time.monotonic() - start) * 1000)

    @staticmethod
    def _is_retryable(status: int) -> bool:
        """True para 429 (rate-limit) y errores 5xx transitorios del servidor."""
        return status == 429 or status >= 500

    def _hold(
        self,
        timestamp_ms: int,
        latency_ms: int,
        request_json: str,
        prompt: Prompt,
        context: DecisionContext,
        *,
        reason: str,
        response_text: str,
        error: str,
    ) -> DecisionResult:
        return DecisionResult(
            decision=TradingDecision.hold(timestamp_ms, reason),
            call=self._record(
                timestamp_ms=timestamp_ms,
                latency_ms=latency_ms,
                request_json=request_json,
                response_text=response_text,
                reported_model="",
                prompt_hash=prompt.hash,
                market_state_hash=context.market_state_hash,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                error=error,
            ),
        )

    def _record(
        self,
        *,
        timestamp_ms: int,
        latency_ms: int,
        request_json: str,
        response_text: str,
        reported_model: str,
        prompt_hash: str,
        market_state_hash: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        error: str,
    ) -> LLMCallRecord:
        return LLMCallRecord(
            provider="deepseek",
            requested_model=self._config.model,
            reported_model_version=reported_model,
            request=request_json,
            response=response_text,
            prompt_hash=prompt_hash,
            market_state_hash=market_state_hash,
            temperature=self._config.temperature,
            parameters=(),
            timestamp_ms=timestamp_ms,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            error=error,
        )

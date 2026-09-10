"""Cliente REST v5 de trading sobre Testnet (PRD §26; Fase 12).

Ciclo completo: crear/cancelar órdenes spot, listar abiertas para reconciliación.
Manejo de errores: retCode != 0 ⇒ BybitTradeError; 429/5xx con backoff limitado
y Retry-After. `order_link_id` propio garantiza idempotencia y reconciliación.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, Field

from domain.trading.order import OrderRequest, OrderStatus
from infrastructure.bybit.auth import BybitSigner

CREATE_PATH = "/v5/order/create"
CANCEL_PATH = "/v5/order/cancel"
OPEN_ORDERS_PATH = "/v5/order/realtime"
_MAX_RETRIES = 3


class BybitTradeError(Exception):
    """Error de la API de trading (retCode != 0 o HTTP agotado)."""


@dataclass(frozen=True, slots=True)
class PlacedOrder:
    """Confirmación de una orden aceptada por el exchange."""

    exchange_order_id: str
    order_link_id: str


class RemoteOrder(BaseModel):
    """Orden vista desde el exchange (para reconciliación)."""

    model_config = {"populate_by_name": True}

    order_link_id: str = Field(alias="orderLinkId")
    exchange_order_id: str = Field(alias="orderId")
    status: OrderStatus
    cumulative_qty: float = Field(default=0.0, alias="cumExecQty")
    avg_price: float | None = Field(default=None, alias="avgPrice")

    @classmethod
    def tolerant(cls, **data: str) -> RemoteOrder:
        """Parseo tolerante a strings vacíos del exchange."""
        clean = {k: v for k, v in data.items() if v not in ("", None)}
        if "cumExecQty" in clean:
            clean["cumExecQty"] = float(clean["cumExecQty"])  # type: ignore[assignment]
        if clean.get("avgPrice"):
            clean["avgPrice"] = float(clean["avgPrice"])  # type: ignore[assignment]
        return cls.model_validate(clean)


class BybitTradeClient:
    """Adaptador REST de ejecución sobre Testnet (nunca producción)."""

    def __init__(
        self,
        *,
        signer: BybitSigner,
        base_url: str = "https://api-testnet.bybit.com",
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        category: str = "spot",
    ) -> None:
        self._signer = signer
        self._category = category
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)

    async def close(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------ órdenes

    async def place_order(self, request: OrderRequest) -> PlacedOrder:
        body: dict[str, object] = {
            "category": self._category,
            "symbol": request.symbol,
            "side": request.side,
            "orderType": request.order_type,
            "qty": f"{request.quantity:.8f}".rstrip("0").rstrip("."),
            "orderLinkId": request.order_link_id,
            "marketUnit": "baseCoin",
        }
        if request.price is not None:
            body["price"] = f"{request.price:.8f}".rstrip("0").rstrip(".")
        result = await self._post(CREATE_PATH, body)
        return PlacedOrder(
            exchange_order_id=str(result.get("orderId", "")),
            order_link_id=str(result.get("orderLinkId", request.order_link_id)),
        )

    async def cancel_order(self, *, symbol: str, order_link_id: str) -> bool:
        """Cancela una orden; False si ya no existe (idempotente)."""
        try:
            await self._post(
                CANCEL_PATH,
                {
                    "category": self._category,
                    "symbol": symbol,
                    "orderLinkId": order_link_id,
                },
            )
            return True
        except BybitTradeError as exc:
            if "110001" in str(exc):  # order not exists / too late to cancel
                return False
            raise

    async def open_orders(self, symbol: str) -> list[RemoteOrder]:
        result = await self._get(
            OPEN_ORDERS_PATH,
            {
                "category": self._category,
                "symbol": symbol,
            },
        )
        rows_raw = result.get("list", [])
        rows: list[dict[str, object]] = (
            [r for r in rows_raw if isinstance(r, dict)] if isinstance(rows_raw, list) else []
        )
        return [
            RemoteOrder.tolerant(
                **{
                    "orderLinkId": str(r.get("orderLinkId", "")),
                    "orderId": str(r.get("orderId", "")),
                    "status": str(r.get("orderStatus", r.get("status", ""))),
                    "cumExecQty": str(r.get("cumExecQty", "")),
                    "avgPrice": str(r.get("avgPrice", "")),
                }
            )
            for r in rows
        ]

    # ------------------------------------------------------------------ HTTP

    async def _post(self, path: str, body: dict[str, object]) -> dict[str, object]:
        import json

        payload = json.dumps(body)
        headers = self._signer.sign(path, payload=payload)
        response = await self._send_with_retry(
            lambda: self._client.post(path, content=payload, headers=headers)
        )
        return self._unwrap(response)

    async def _get(self, path: str, params: dict[str, str]) -> dict[str, object]:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        headers = self._signer.sign(path, payload=query)

        async def send() -> httpx.Response:
            return await self._client.get(path, params=params, headers=headers)

        return self._unwrap(await self._send_with_retry(send))

    @staticmethod
    def _unwrap(response: httpx.Response) -> dict[str, object]:
        raw: dict[str, object] = response.json()
        if raw.get("retCode") != 0:
            raise BybitTradeError(f"retCode={raw.get('retCode')}: {raw.get('retMsg')}")
        result = raw.get("result")
        return result if isinstance(result, dict) else {}

    async def _send_with_retry(
        self, send: Callable[[], Awaitable[httpx.Response]]
    ) -> httpx.Response:
        last_status = 0
        for attempt in range(_MAX_RETRIES + 1):
            response = await send()
            if response.status_code == 429 or response.status_code >= 500:
                last_status = response.status_code
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(2**attempt, 8)
                delay += random.uniform(0, 0.25)
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(delay)
                    continue
                break
            return response
        raise BybitTradeError(f"HTTP {last_status} tras {_MAX_RETRIES + 1} intentos")

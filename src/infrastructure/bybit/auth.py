"""Autenticación Bybit v5 (Testnet): firma HMAC-SHA256 (skill bybit-integration).

sign_payload = timestamp + api_key + recv_window + (query_string | json_payload)
Firma = HMAC_SHA256(api_secret, sign_payload) en hex. Credenciales SOLO vía .env.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass


class BybitSigner:
    """Firmante determinista de cabeceras X-BAPI-* para la API v5."""

    def __init__(self, *, api_key: str, api_secret: str, recv_window: int = 10_000) -> None:
        self._api_key = api_key
        self._api_secret = api_secret.encode("utf-8")
        self._recv_window = recv_window

    def sign(
        self,
        path: str,
        *,
        payload: str,
        timestamp_ms: int | None = None,
    ) -> dict[str, str]:
        ts = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
        sign_payload = f"{ts}{self._api_key}{self._recv_window}{payload}"
        signature = hmac.new(self._api_secret, sign_payload.encode("utf-8"), hashlib.sha256)
        return {
            "X-BAPI-API-KEY": self._api_key,
            "X-BAPI-TIMESTAMP": str(ts),
            "X-BAPI-RECV-WINDOW": str(self._recv_window),
            "X-BAPI-SIGN": signature.hexdigest(),
            "Content-Type": "application/json",
        }


@dataclass(frozen=True, slots=True)
class BybitCredentials:
    """Credenciales cargadas desde Settings/.env; nunca se versionan."""

    api_key: str
    api_secret: str

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key) and bool(self.api_secret)

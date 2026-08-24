"""Supervisor de conexión con backoff exponencial acotado (Fase 12).

Envuelve cualquier operación `connect` asíncrona (WS privado de trade): reintenta
con backoff exponencial + tope y ejecuta `on_reconnect` tras cada recuperación —
el punto natural para disparar la reconciliación de órdenes.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SupervisorConfig:
    max_attempts: int = 5
    initial_backoff: float = 1.0
    max_backoff: float = 30.0

    def delay_for(self, attempt: int) -> float:
        raw = min(self.initial_backoff * (2**attempt), self.max_backoff)
        delay = min(raw + random.uniform(0, raw * 0.1), self.max_backoff)
        return float(delay)


class ConnectionSupervisor:
    """Reconecta una sesión con techo de intentos; gancho on_reconnect."""

    def __init__(
        self,
        config: SupervisorConfig,
        *,
        connect: Callable[[], Awaitable[None]],
        on_reconnect: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._config = config
        self._connect = connect
        self._on_reconnect = on_reconnect
        self.attempts = 0

    async def run_once_until_connected(self) -> None:
        """Intenta conectar hasta `max_attempts`; lanza el último error si agota."""
        last_error: Exception | None = None
        failed_before = False
        for attempt in range(self._config.max_attempts):
            try:
                await self._connect()
            except Exception as exc:  # noqa: BLE001 - reintento deliberado de red
                last_error = exc
                failed_before = True
                self.attempts = attempt + 1
                if attempt < self._config.max_attempts - 1:
                    await asyncio.sleep(self._config.delay_for(attempt))
                continue
            self.attempts = attempt + 1
            if failed_before and self._on_reconnect is not None:
                await self._on_reconnect()
            return
        assert last_error is not None
        raise last_error

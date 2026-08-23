"""Puertos de persistencia (Protocols) definidos por la capa de aplicación."""

from __future__ import annotations

from typing import Any, Protocol


class SystemStateRepository(Protocol):
    """Acceso a estado global del sistema (clave/valor)."""

    async def get(self, key: str) -> dict[str, Any] | None:
        """Devuelve el valor asociado a `key`, o None si no existe."""
        ...

    async def set(self, key: str, value: dict[str, Any]) -> None:
        """Crea o actualiza el valor asociado a `key`."""
        ...

    async def ping(self) -> bool:
        """Verifica conectividad con la base de datos (readiness)."""
        ...

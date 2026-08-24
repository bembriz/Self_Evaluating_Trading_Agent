"""Puerto de persistencia y recuperación de la Trading Memory (PRD §32-34)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from domain.memory.memory import TradingMemory
from domain.memory.reflection import Reflection


@dataclass(frozen=True, slots=True)
class ScoredMemory:
    """Memoria recuperada con su similitud coseno respecto a la consulta."""

    memory: TradingMemory
    similarity: float


@runtime_checkable
class MemoryRepository(Protocol):
    """Almacén vectorial. Toda búsqueda impone el filtro temporal anti-leakage."""

    async def save_memory(self, item: TradingMemory) -> None:
        """Inserta (o reemplaza por id) una memoria con su embedding."""
        ...

    async def save_reflection(self, reflection: Reflection) -> None:
        """Persiste una reflexión de trade cerrado."""
        ...

    async def search_similar(
        self,
        query_embedding: Sequence[float],
        *,
        k: int,
        decision_timestamp_ms: int,
        embedding_space: str,
    ) -> list[ScoredMemory]:
        """Top-k por similitud coseno con `outcome_timestamp < decision_timestamp`.

        El filtro temporal es OBLIGATORIO y viaja siempre junto a la similitud.
        """
        ...

    async def count_memories(self) -> int:
        """Número total de memorias almacenadas."""
        ...

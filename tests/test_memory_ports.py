"""Tests de los puertos de memoria y embeddings (Fase 09)."""

from collections.abc import Sequence

from application.ports.embeddings import EmbeddingProvider
from application.ports.memory_repository import MemoryRepository, ScoredMemory
from domain.memory.memory import TradingMemory
from domain.memory.reflection import Reflection


class FakeEmbeddingProvider:
    @property
    def model_name(self) -> str:
        return "fake-e5"

    @property
    def dimension(self) -> int:
        return 4

    def embed(self, texts: Sequence[str], *, is_query: bool = False) -> list[list[float]]:
        return [[0.1] * 4 for _ in texts]


class FakeMemoryRepository:
    async def save_memory(self, item: TradingMemory) -> None: ...

    async def save_reflection(self, reflection: Reflection) -> None: ...

    async def search_similar(
        self,
        query_embedding: Sequence[float],
        *,
        k: int,
        decision_timestamp_ms: int,
        embedding_space: str,
    ) -> list[ScoredMemory]:
        return []

    async def count_memories(self) -> int:
        return 0


def test_embedding_provider_protocol_structural() -> None:
    assert isinstance(FakeEmbeddingProvider(), EmbeddingProvider)


def test_memory_repository_protocol_structural() -> None:
    assert isinstance(FakeMemoryRepository(), MemoryRepository)

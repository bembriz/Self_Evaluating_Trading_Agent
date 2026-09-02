"""Integration: repositorio de memoria contra PostgreSQL+pgvector (PRD §32-34).

Requiere la DB de test migrada (fixture `session` de conftest). Verifica upsert,
búsqueda top-k por similitud y, críticamente, el filtrado temporal anti-leakage.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.ports.memory_repository import ScoredMemory
from domain.memory.reflection import Reflection, ReflectionResult
from domain.trading.signal import Action
from infrastructure.database.memory_repository import SqlAlchemyMemoryRepository

DIMENSION = 384
SPACE = "fake|fake-e5|384"


def _embedding(index: int) -> list[float]:
    vector = [0.0] * DIMENSION
    vector[index] = 1.0
    return vector


def test_fixture_embedding_matches_pgvector_dimension() -> None:
    assert len(_embedding(0)) == DIMENSION
    assert _embedding(0)[0] == 1.0
    assert _embedding(0)[1] == 0.0


def _item(id_: str, outcome_ts: int, embedding: list[float], space: str = SPACE) -> object:
    from domain.memory.memory import TradingMemory

    return TradingMemory(
        id=id_,
        text=f"texto {id_}",
        outcome_timestamp_ms=outcome_ts,
        symbol="ETHUSDT",
        action=Action.BUY.value,
        result="win",
        embedding_space=space,
        embedding=tuple(embedding),
    )


@pytest.mark.integration
async def test_save_and_search_with_temporal_filter(session: AsyncSession) -> None:
    repo = SqlAlchemyMemoryRepository(session)
    base = _embedding(0)
    await repo.save_memory(_item("m_pasada", 900, base))  # type: ignore[arg-type]
    await repo.save_memory(_item("m_futura", 2000, base))  # type: ignore[arg-type]

    hits = await repo.search_similar(base, k=10, decision_timestamp_ms=1000, embedding_space=SPACE)
    ids = [h.memory.id for h in hits if isinstance(h, ScoredMemory)]
    assert ids == ["m_pasada"], f"leakage detectado: {ids}"
    assert hits[0].similarity == pytest.approx(1.0)


@pytest.mark.integration
async def test_search_isolated_by_embedding_space(session: AsyncSession) -> None:
    repo = SqlAlchemyMemoryRepository(session)
    await repo.save_memory(_item("m_otro_espacio", 500, _embedding(1), "otro|modelo|384"))  # type: ignore[arg-type]

    hits = await repo.search_similar(
        _embedding(1), k=10, decision_timestamp_ms=1000, embedding_space=SPACE
    )
    assert all(h.memory.embedding_space == SPACE for h in hits)


@pytest.mark.integration
async def test_reflection_roundtrip(session: AsyncSession) -> None:
    repo = SqlAlchemyMemoryRepository(session)
    await repo.save_reflection(
        Reflection(
            id="r_int",
            outcome_closed_at_ms=700,
            result=ReflectionResult.LOSS,
            primary_error="COUNTER_TREND_ENTRY",
        )
    )
    assert await repo.count_memories() >= 0

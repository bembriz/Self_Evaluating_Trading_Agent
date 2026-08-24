"""Repositorio de Trading Memory sobre SQLAlchemy + pgvector (PRD §32-34).

Regla dura: la búsqueda por similitud SIEMPRE viaja con el filtro temporal
`outcome_timestamp_ms < decision_timestamp_ms` y con el espacio de embeddings
versionado; la similitud nunca se consulta sola.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from application.ports.memory_repository import ScoredMemory
from domain.memory.guards import assert_no_leakage
from domain.memory.memory import TradingMemory
from domain.memory.reflection import Reflection
from infrastructure.database.models import MemoryItemRecord, ReflectionRecord


class SqlAlchemyMemoryRepository:
    """Implementación de MemoryRepository con distancia coseno de pgvector."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_memory(self, item: TradingMemory) -> None:
        if len(item.embedding) == 0 or not item.embedding_space:
            raise ValueError("memoria sin embedding o sin espacio versionado")
        row = await self._session.get(MemoryItemRecord, item.id)
        values = {
            "text": item.text,
            "outcome_timestamp_ms": item.outcome_timestamp_ms,
            "symbol": item.symbol,
            "action": item.action,
            "result": item.result,
            "pnl": item.pnl,
            "mfe": item.mfe,
            "mae": item.mae,
            "fees": item.fees,
            "slippage": item.slippage,
            "reflection": item.reflection,
            "strategy_version": item.strategy_version,
            "prompt_version": item.prompt_version,
            "llm_model": item.llm_model,
            "experiment_id": item.experiment_id,
            "embedding_space": item.embedding_space,
            "embedding": list(item.embedding),
        }
        if row is None:
            self._session.add(MemoryItemRecord(id=item.id, **values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
        await self._session.flush()

    async def save_reflection(self, reflection: Reflection) -> None:
        row = await self._session.get(ReflectionRecord, reflection.id)
        if row is None:
            self._session.add(
                ReflectionRecord(
                    id=reflection.id,
                    outcome_closed_at_ms=reflection.outcome_closed_at_ms,
                    result=reflection.result.value,
                    primary_error=reflection.primary_error,
                    lesson=reflection.lesson,
                    future_condition=reflection.future_condition,
                )
            )
        else:
            row.outcome_closed_at_ms = reflection.outcome_closed_at_ms
            row.result = reflection.result.value
            row.primary_error = reflection.primary_error
            row.lesson = reflection.lesson
            row.future_condition = reflection.future_condition
        await self._session.flush()

    async def search_similar(
        self,
        query_embedding: Sequence[float],
        *,
        k: int,
        decision_timestamp_ms: int,
        embedding_space: str,
    ) -> list[ScoredMemory]:
        distance = MemoryItemRecord.embedding.cosine_distance(list(query_embedding))
        stmt = (
            select(MemoryItemRecord, distance.label("distance"))
            .where(
                MemoryItemRecord.outcome_timestamp_ms < decision_timestamp_ms,
                MemoryItemRecord.embedding_space == embedding_space,
            )
            .order_by(distance)
            .limit(k)
        )
        rows = (await self._session.execute(stmt)).all()
        scored = [
            ScoredMemory(memory=_to_domain(row), similarity=1.0 - float(distance_))
            for row, distance_ in rows
        ]
        # Defensa en profundidad: el filtro SQL es obligatorio; el guard del dominio
        # garantiza el invariante incluso ante cambios futuros de la query.
        assert_no_leakage((s.memory for s in scored), decision_timestamp_ms=decision_timestamp_ms)
        return scored

    async def count_memories(self) -> int:
        stmt = select(func.count()).select_from(MemoryItemRecord)
        return int(await self._session.scalar(stmt) or 0)


def _to_domain(row: MemoryItemRecord) -> TradingMemory:
    return TradingMemory(
        id=row.id,
        text=row.text,
        outcome_timestamp_ms=row.outcome_timestamp_ms,
        symbol=row.symbol,
        action=row.action,
        result=row.result,
        pnl=row.pnl,
        mfe=row.mfe,
        mae=row.mae,
        fees=row.fees,
        slippage=row.slippage,
        reflection=row.reflection,
        strategy_version=row.strategy_version,
        prompt_version=row.prompt_version,
        llm_model=row.llm_model,
        experiment_id=row.experiment_id,
        embedding_space=row.embedding_space,
        embedding=tuple(row.embedding) if row.embedding is not None else (),
    )

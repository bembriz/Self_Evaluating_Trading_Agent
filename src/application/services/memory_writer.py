"""Inserción de reflexiones en la Trading Memory (PRD §34-35).

Regla dura: una reflexión solo entra en memoria cuando el trade correspondiente
ha TERMINADO (outcome cerrado) y nunca puede violar el filtro temporal
`outcome_timestamp < decision_timestamp` para decisiones futuras.
"""

from __future__ import annotations

from application.ports.embeddings import EmbeddingProvider
from application.ports.memory_repository import MemoryRepository
from domain.evaluation.outcome import TradeOutcome
from domain.memory.guards import assert_no_leakage
from domain.memory.memory import TradingMemory
from domain.memory.reflection import Reflection


class MemoryWriter:
    """Persiste reflexiones como items de memoria con embedding y versiones."""

    def __init__(
        self,
        *,
        embeddings: EmbeddingProvider,
        repository: MemoryRepository,
        embedding_space: str,
        strategy_version: str,
        prompt_version: str,
        llm_model: str,
        experiment_id: str,
    ) -> None:
        self._embeddings = embeddings
        self._repo = repository
        self._space = embedding_space
        self._strategy_version = strategy_version
        self._prompt_version = prompt_version
        self._llm_model = llm_model
        self._experiment_id = experiment_id

    async def persist(
        self,
        *,
        reflection: Reflection,
        outcome: TradeOutcome,
        decision_timestamp_ms: int | None = None,
    ) -> TradingMemory:
        """Inserta la reflexión como memoria; exige outcome cerrado y sin leakage."""
        if reflection.outcome_closed_at_ms < outcome.trade.exit_ts:
            raise ValueError("reflexión de trade no cerrado: outcome posterior a la reflexión")

        text = (
            f"{reflection.result.value.upper()} {outcome.trade.entry_price:g}->"
            f"{outcome.trade.exit_price:g} mfe={outcome.mfe:g} mae={outcome.mae:g}. "
            f"Lección: {reflection.lesson or 'n/a'} "
            f"Condición futura: {reflection.future_condition or 'n/a'}."
        ).strip()
        vector = self._embeddings.embed([text], is_query=False)[0]
        memory = TradingMemory(
            id=reflection.id,
            text=text,
            outcome_timestamp_ms=reflection.outcome_closed_at_ms,
            symbol="",
            action="",
            result=outcome.result.value,
            pnl=outcome.trade.net_pnl,
            mfe=outcome.mfe,
            mae=outcome.mae,
            fees=outcome.trade.fees,
            slippage=outcome.trade.slippage,
            reflection=reflection.lesson,
            strategy_version=self._strategy_version,
            prompt_version=self._prompt_version,
            llm_model=self._llm_model,
            experiment_id=self._experiment_id,
            embedding_space=self._space,
            embedding=tuple(vector),
        )
        if decision_timestamp_ms is not None:
            # Defensa explícita: esta memoria jamás podrá alimentar decisiones previas.
            assert_no_leakage([memory], decision_timestamp_ms=decision_timestamp_ms)

        await self._repo.save_reflection(reflection)
        await self._repo.save_memory(memory)
        return memory

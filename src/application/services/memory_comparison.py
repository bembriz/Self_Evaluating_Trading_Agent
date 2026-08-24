"""Comparador LLM vs LLM+Memory (Fase 09, PRD §79): mismo estado, dos brazos.

Ejecuta cada decisión dos veces — sin memorias y con las memorias recuperadas —
aplicando SIEMPRE el guard anti-leakage del dominio antes de inyectarlas.
La ejecución real contra DeepSeek queda pendiente de `DEEPSEEK_API_KEY`
(decisión del usuario); el servicio es agnóstico del provider.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from application.services.decision_agent import DecisionAgent
from domain.market.state import MarketState
from domain.memory.guards import MemoryLeakageError, assert_no_leakage
from domain.memory.memory import TradingMemory
from domain.trading.decision import DecisionContext, TradingDecision

Retriever = Callable[[MarketState], Awaitable[Sequence[TradingMemory]]]


@dataclass(frozen=True, slots=True)
class PairedDecision:
    """Par de decisiones sobre el mismo estado de mercado."""

    timestamp_ms: int
    without_memory: TradingDecision
    with_memory: TradingDecision


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    """Resultado agregado de la comparativa."""

    pairs: tuple[PairedDecision, ...]
    leakage_errors: tuple[MemoryLeakageError, ...]

    @staticmethod
    def _counts(decisions: Sequence[TradingDecision]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for d in decisions:
            key = d.action.value
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))

    @property
    def without_memory_counts(self) -> dict[str, int]:
        return self._counts([p.without_memory for p in self.pairs])

    @property
    def with_memory_counts(self) -> dict[str, int]:
        return self._counts([p.with_memory for p in self.pairs])


class MemoryComparison:
    """Orquesta los dos brazos de la comparativa sobre una secuencia de estados."""

    def __init__(self, agent: DecisionAgent, retrieve: Retriever) -> None:
        self._agent = agent
        self._retrieve = retrieve

    async def run(self, states: Sequence[MarketState]) -> ComparisonResult:
        pairs: list[PairedDecision] = []
        leakage_errors: list[MemoryLeakageError] = []
        for state in states:
            context = DecisionContext(symbol=state.symbol, timestamp_ms=state.timestamp_ms)
            memories: Sequence[TradingMemory] = []
            try:
                memories = await self._retrieve(state)
                assert_no_leakage(memories, decision_timestamp_ms=state.timestamp_ms)
            except MemoryLeakageError as exc:
                leakage_errors.append(exc)
                memories = []
            without_memory = await self._agent.decide(state, [], context)
            with_memory = await self._agent.decide(state, memories, context)
            pairs.append(
                PairedDecision(
                    timestamp_ms=state.timestamp_ms,
                    without_memory=without_memory,
                    with_memory=with_memory,
                )
            )
        return ComparisonResult(pairs=tuple(pairs), leakage_errors=tuple(leakage_errors))

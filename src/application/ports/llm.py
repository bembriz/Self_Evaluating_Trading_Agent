"""Puertos de aplicación del LLM Decision Agent (Protocols, PRD §17–20).

Contrato de I/O entre el servicio de dominio y los adaptadores de
infraestructura: el proveedor LLM que emite decisiones y el almacén de prompts
versionados. Definidos como `Protocol` `@runtime_checkable` para verificación
estructural sin acoplar a una implementación concreta.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from domain.llm.call import LLMCallRecord
from domain.llm.prompt import Prompt
from domain.market.state import MarketState
from domain.memory.memory import TradingMemory
from domain.trading.decision import DecisionContext, TradingDecision


@dataclass(frozen=True, slots=True)
class DecisionResult:
    """Resultado de una decisión: la decisión estructurada y su llamada LLM."""

    decision: TradingDecision
    call: LLMCallRecord


@runtime_checkable
class LLMProvider(Protocol):
    """Proveedor LLM que convierte estado de mercado en una decisión estructurada."""

    async def decide(
        self,
        market_state: MarketState,
        memories: Sequence[TradingMemory],
        context: DecisionContext,
        prompt: Prompt,
    ) -> DecisionResult: ...


@runtime_checkable
class PromptStore(Protocol):
    """Almacén de prompts versionados por ``kind``."""

    def load(self, kind: str, version: str) -> Prompt: ...


class PromptNotFound(Exception):
    """Se lanza cuando no existe el prompt solicitado (kind, version)."""

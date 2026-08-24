"""DecisionAgent (PRD §37-38): orquestador del flujo de decisión LLM.

Servicio de aplicación que une provider + prompt_store + cost_monitor, imponiendo el
fail-safe HOLD: si el presupuesto está agotado, si el prompt no existe, o si el
proveedor lanza una excepción, devuelve una decisión HOLD de seguridad sin gastar.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from application.ports.llm import LLMProvider, PromptNotFound, PromptStore
from application.services.cost_monitor import CostMonitor
from domain.market.state import MarketState
from domain.memory.memory import TradingMemory
from domain.trading.decision import DecisionContext, TradingDecision


@dataclass(frozen=True, slots=True)
class DecisionAgentConfig:
    """Configuración inmutable del agente: prompt a cargar por defecto."""

    prompt_kind: str = "decision"
    default_prompt_version: str = "v001"


class DecisionAgent:
    """Orquesta provider, prompt_store y cost_monitor con fail-safe HOLD."""

    def __init__(
        self,
        provider: LLMProvider,
        prompt_store: PromptStore,
        cost_monitor: CostMonitor,
        config: DecisionAgentConfig | None = None,
    ) -> None:
        self._provider = provider
        self._prompt_store = prompt_store
        self._cost_monitor = cost_monitor
        self._config = config or DecisionAgentConfig()

    async def decide(
        self,
        market_state: MarketState,
        memories: Sequence[TradingMemory],
        context: DecisionContext,
    ) -> TradingDecision:
        if self._cost_monitor.is_blocked():
            return TradingDecision.hold(context.timestamp_ms, "budget_exhausted")
        try:
            prompt = self._prompt_store.load(
                self._config.prompt_kind,
                context.prompt_version or self._config.default_prompt_version,
            )
            result = await self._provider.decide(market_state, memories, context, prompt)
        except PromptNotFound:
            return TradingDecision.hold(context.timestamp_ms, "prompt_not_found")
        except Exception as exc:
            return TradingDecision.hold(
                context.timestamp_ms, f"provider_error:{type(exc).__name__}"
            )
        self._cost_monitor.record(result.call)
        return result.decision

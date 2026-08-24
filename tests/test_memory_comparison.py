"""Tests del comparador LLM vs LLM+Memory (Fase 09, PRD §79)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from application.ports.llm import DecisionResult
from application.services.cost_monitor import CostMonitor
from application.services.decision_agent import DecisionAgent
from application.services.memory_comparison import MemoryComparison
from domain.llm.call import LLMCallRecord
from domain.llm.prompt import Prompt
from domain.market.orderbook import MarketDataHealth
from domain.market.state import MarketState
from domain.memory.guards import MemoryLeakageError
from domain.memory.memory import TradingMemory
from domain.trading.decision import DecisionContext, TradingDecision
from domain.trading.signal import Action


def _call(cost: float) -> LLMCallRecord:
    return LLMCallRecord(
        provider="fake",
        requested_model="m",
        reported_model_version="v",
        request="{}",
        response="{}",
        prompt_hash="h",
        market_state_hash="ms",
        temperature=0.0,
        parameters=(),
        timestamp_ms=0,
        latency_ms=1,
        input_tokens=10,
        output_tokens=10,
        cost_usd=cost,
    )


def _state(ts: int) -> MarketState:
    return MarketState(
        symbol="ETHUSDT",
        timestamp_ms=ts,
        health=MarketDataHealth.HEALTHY,
        regime=None,
        timeframes={},
        orderbook=None,
        btc=None,
    )


class MemoryAwareProvider:
    """BUY si hay memorias; HOLD si no: permite verificar ambos caminos."""

    def __init__(self) -> None:
        self.seen_memory_counts: list[int] = []

    async def decide(
        self,
        market_state: MarketState,
        memories: Sequence[TradingMemory],
        context: DecisionContext,
        prompt: Prompt,
    ) -> DecisionResult:
        self.seen_memory_counts.append(len(memories))
        action = Action.BUY if memories else Action.HOLD
        d = TradingDecision(timestamp_ms=context.timestamp_ms, action=action, confidence=0.8)
        return DecisionResult(d, _call(cost=0.01))


class EmptyStore:
    def load(self, kind: str, version: str) -> Prompt:
        return Prompt(kind=kind, version=version, text="t")


async def test_comparison_runs_both_arms_and_counts() -> None:
    provider = MemoryAwareProvider()
    monitor = CostMonitor(experiment_budget_usd=10.0, monthly_budget_usd=100.0)
    agent = DecisionAgent(provider, EmptyStore(), monitor)

    past = TradingMemory(id="m1", text="lección", outcome_timestamp_ms=500)

    async def retrieve(state: MarketState) -> Sequence[TradingMemory]:
        # Guard anti-leakage aplicado por el propio comparador en producción.
        return [past] if state.timestamp_ms > past.outcome_timestamp_ms else []

    comparison = MemoryComparison(agent=agent, retrieve=retrieve)
    result = await comparison.run([_state(100), _state(1000)])

    assert len(result.pairs) == 2
    # Sin memoria -> HOLD; con memoria -> BUY.
    assert result.pairs[1].without_memory.action is Action.HOLD
    assert result.pairs[1].with_memory.action is Action.BUY
    assert provider.seen_memory_counts == [0, 0, 0, 1]
    assert result.without_memory_counts["hold"] == 2
    assert result.with_memory_counts == {"buy": 1, "hold": 1}
    assert monitor.total_cost_usd == pytest.approx(0.04)


async def test_leakage_guard_blocks_future_memory() -> None:
    provider = MemoryAwareProvider()
    monitor = CostMonitor(experiment_budget_usd=10.0, monthly_budget_usd=100.0)
    agent = DecisionAgent(provider, EmptyStore(), monitor)
    future = TradingMemory(id="futuro", text="x", outcome_timestamp_ms=500)

    async def bad_retrieve(state: MarketState) -> Sequence[TradingMemory]:
        return [future]

    comparison = MemoryComparison(agent=agent, retrieve=bad_retrieve)
    result = await comparison.run([_state(100)])
    assert isinstance(result.leakage_errors[0], MemoryLeakageError)

from collections.abc import Sequence

from application.ports.llm import DecisionResult, PromptNotFound
from application.services.cost_monitor import CostMonitor
from application.services.decision_agent import DecisionAgent, DecisionAgentConfig
from domain.llm.call import LLMCallRecord
from domain.llm.prompt import Prompt
from domain.market.orderbook import MarketDataHealth
from domain.market.state import MarketState
from domain.memory.memory import TradingMemory
from domain.trading.decision import DecisionContext, TradingDecision
from domain.trading.signal import Action


def _call(cost: float = 1.0, error: str = "") -> LLMCallRecord:
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
        input_tokens=100,
        output_tokens=100,
        cost_usd=cost,
        error=error,
    )


def _market_state() -> MarketState:
    return MarketState(
        symbol="ETHUSDT",
        timestamp_ms=1000,
        health=MarketDataHealth.HEALTHY,
        regime=None,
        timeframes={},
        orderbook=None,
        btc=None,
    )


def _ctx() -> DecisionContext:
    return DecisionContext(symbol="ETHUSDT", timestamp_ms=1000)


class FakeProvider:
    def __init__(self, result: DecisionResult | None = None, exc: Exception | None = None) -> None:
        self.result = result
        self.exc = exc
        self.called = False

    async def decide(
        self,
        market_state: MarketState,
        memories: Sequence[TradingMemory],
        context: DecisionContext,
        prompt: Prompt,
    ) -> DecisionResult:
        self.called = True
        if self.exc:
            raise self.exc
        assert self.result is not None
        return self.result


class FakePromptStore:
    def __init__(self) -> None:
        self.requested: tuple[str, str] | None = None

    def load(self, kind: str, version: str) -> Prompt:
        self.requested = (kind, version)
        return Prompt(kind=kind, version=version, text="t")


class Missing:
    def load(self, kind: str, version: str) -> Prompt:
        raise PromptNotFound("x")


async def test_decision_recorded_and_returned() -> None:
    d = TradingDecision(timestamp_ms=1000, action=Action.BUY, confidence=0.7)
    provider = FakeProvider(result=DecisionResult(d, _call(cost=2.0)))
    store = FakePromptStore()
    monitor = CostMonitor(experiment_budget_usd=10.0, monthly_budget_usd=100.0)
    agent = DecisionAgent(provider, store, monitor, DecisionAgentConfig())
    out = await agent.decide(_market_state(), [], _ctx())
    assert out is d
    assert monitor.total_cost_usd == 2.0
    assert provider.called is True
    assert store.requested == ("decision", "v001")


async def test_budget_blocked_returns_hold_without_calling() -> None:
    d = TradingDecision(timestamp_ms=1000, action=Action.BUY, confidence=0.7)
    provider = FakeProvider(result=DecisionResult(d, _call(cost=0.0)))
    monitor = CostMonitor(experiment_budget_usd=1.0, monthly_budget_usd=100.0)
    monitor.record(_call(cost=1.0))  # agota experiment budget
    agent = DecisionAgent(provider, FakePromptStore(), monitor)
    out = await agent.decide(_market_state(), [], _ctx())
    assert out.is_fallback is True
    assert out.fallback_reason == "budget_exhausted"
    assert provider.called is False


async def test_provider_exception_returns_hold() -> None:
    provider = FakeProvider(exc=RuntimeError("boom"))
    monitor = CostMonitor(experiment_budget_usd=10.0, monthly_budget_usd=100.0)
    agent = DecisionAgent(provider, FakePromptStore(), monitor)
    out = await agent.decide(_market_state(), [], _ctx())
    assert out.is_fallback is True
    assert "RuntimeError" in (out.fallback_reason or "")


async def test_prompt_not_found_returns_hold() -> None:
    monitor = CostMonitor(experiment_budget_usd=10.0, monthly_budget_usd=100.0)
    agent = DecisionAgent(FakeProvider(), Missing(), monitor)
    out = await agent.decide(_market_state(), [], _ctx())
    assert out.is_fallback is True
    assert out.fallback_reason == "prompt_not_found"

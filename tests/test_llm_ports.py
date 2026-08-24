from collections.abc import Sequence

from application.ports.llm import DecisionResult, LLMProvider, PromptStore
from domain.llm.call import LLMCallRecord
from domain.llm.prompt import Prompt
from domain.market.state import MarketState
from domain.memory.memory import TradingMemory
from domain.trading.decision import DecisionContext, TradingDecision
from domain.trading.signal import Action


def _call() -> LLMCallRecord:
    return LLMCallRecord(
        provider="fake",
        requested_model="m",
        reported_model_version="m-v1",
        request="{}",
        response="{}",
        prompt_hash="h",
        market_state_hash="ms",
        temperature=0.0,
        parameters=(),
        timestamp_ms=0,
        latency_ms=1,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
    )


def test_decision_result_carries_decision_and_call() -> None:
    d = TradingDecision(timestamp_ms=0, action=Action.HOLD, confidence=0.0)
    r = DecisionResult(decision=d, call=_call())
    assert r.decision is d
    assert r.call.input_tokens == 0


class FakeProvider:
    async def decide(
        self,
        market_state: MarketState,
        memories: Sequence[TradingMemory],
        context: DecisionContext,
        prompt: Prompt,
    ) -> DecisionResult:
        raise NotImplementedError


class FakePromptStore:
    def load(self, kind: str, version: str) -> Prompt:
        raise NotImplementedError


def test_protocols_are_structurally_satisfied() -> None:
    # LLMProvider y PromptStore se declaran @runtime_checkable: isinstance() verifica
    # la forma estructural (presencia de los métodos del Protocol).
    assert isinstance(FakeProvider(), LLMProvider)
    assert isinstance(FakePromptStore(), PromptStore)

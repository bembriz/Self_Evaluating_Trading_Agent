from domain.trading.decision import DecisionContext, TradingDecision
from domain.trading.signal import Action, Intensity


def test_decision_factory_and_defaults() -> None:
    d = TradingDecision(timestamp_ms=1000, action=Action.BUY, confidence=0.73)
    assert d.action is Action.BUY
    assert d.intensity is Intensity.MEDIUM
    assert d.supporting_factors == ()
    assert d.fallback_reason is None
    assert d.is_fallback is False


def test_hold_is_fallback() -> None:
    d = TradingDecision.hold(timestamp_ms=5, reason="budget_exhausted")
    assert d.action is Action.HOLD
    assert d.confidence == 0.0
    assert d.is_fallback is True
    assert d.fallback_reason == "budget_exhausted"


def test_context_defaults() -> None:
    c = DecisionContext(symbol="ETHUSDT", timestamp_ms=42)
    assert c.prompt_version == ""
    assert c.market_state_hash == ""

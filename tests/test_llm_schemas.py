import pytest
from pydantic import ValidationError

from domain.trading.signal import Action, Intensity
from infrastructure.llm.schemas import DecisionResponse, DeepSeekChatResponse


def test_valid_decision_parses() -> None:
    d = DecisionResponse.model_validate(
        {
            "decision": "BUY",
            "confidence": 0.73,
            "intensity": "MEDIUM",
            "rationale_summary": "momentum",
            "supporting_factors": ["MACD_BULLISH"],
            "risk_factors": ["BTC_WEAK"],
        }
    )
    td = d.to_decision(timestamp_ms=7)
    assert td.action is Action.BUY
    assert td.intensity is Intensity.MEDIUM
    assert td.confidence == 0.73
    assert td.supporting_factors == ("MACD_BULLISH",)


@pytest.mark.parametrize(
    "payload",
    [
        {"decision": "FOMO", "confidence": 0.5, "intensity": "MEDIUM"},
        {"decision": "BUY", "confidence": 1.5, "intensity": "MEDIUM"},
        {"decision": "BUY", "confidence": -0.1, "intensity": "MEDIUM"},
        {"decision": "BUY", "confidence": 0.5, "intensity": "EXTREME"},
        {"decision": "BUY", "intensity": "MEDIUM"},  # falta confidence
        {},
    ],
)
def test_invalid_decision_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DecisionResponse.model_validate(payload)


def test_confidence_bounds_exact_edges_accepted() -> None:
    DecisionResponse.model_validate({"decision": "HOLD", "confidence": 0.0, "intensity": "LOW"})
    DecisionResponse.model_validate({"decision": "HOLD", "confidence": 1.0, "intensity": "HIGH"})


def test_deepseek_chat_response_parses() -> None:
    raw = {
        "model": "deepseek-v4-flash",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": '{"decision":"HOLD","confidence":0.1,"intensity":"LOW"}',
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    r = DeepSeekChatResponse.model_validate(raw)
    assert r.model == "deepseek-v4-flash"
    assert r.usage.prompt_tokens == 10
    assert r.choices[0].message.content.startswith("{")

"""Esquemas de validación de la salida JSON estructurada del LLM Decision Agent.

Pydantic v2 sólo en `infrastructure/`: valida de forma estricta el payload
emitido por el proveedor LLM (PRD §19-20) y lo convierte al contrato de dominio
`TradingDecision` vía `DecisionResponse.to_decision`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from domain.trading.decision import TradingDecision
from domain.trading.signal import Action, Intensity


class DecisionResponse(BaseModel):
    decision: Literal["BUY", "SELL", "HOLD"]
    confidence: float = Field(ge=0.0, le=1.0)
    intensity: Literal["LOW", "MEDIUM", "HIGH"]
    rationale_summary: str = ""
    supporting_factors: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)

    def to_decision(self, timestamp_ms: int) -> TradingDecision:
        return TradingDecision(
            timestamp_ms=timestamp_ms,
            action=Action[self.decision],
            confidence=self.confidence,
            intensity=Intensity[self.intensity],
            rationale_summary=self.rationale_summary,
            supporting_factors=tuple(self.supporting_factors),
            risk_factors=tuple(self.risk_factors),
        )


class ChatMessage(BaseModel):
    role: str
    content: str


class Choice(BaseModel):
    message: ChatMessage


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0


class DeepSeekChatResponse(BaseModel):
    model: str = ""
    choices: list[Choice] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)

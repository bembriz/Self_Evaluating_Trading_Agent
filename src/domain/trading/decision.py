"""Contrato de decisión del LLM Decision Agent (PRD §19, §37-38). Dominio puro.

Tipos inmutables con cero I/O y cero frameworks: sólo `dataclasses` y tipos de la
stdlib. Reutiliza `Action` e `Intensity` de `domain.trading.signal`.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.trading.signal import Action, Intensity


@dataclass(frozen=True, slots=True)
class DecisionContext:
    """Contexto de entrada para el LLM en el instante `timestamp_ms`.

    Los campos opcionales permiten trazar qué experimento, versión de prompt y
    estado de mercado produjeron una decisión (reproducibilidad y no-lookahead).
    """

    symbol: str
    timestamp_ms: int
    experiment_id: str = ""
    prompt_version: str = ""
    market_state_hash: str = ""


@dataclass(frozen=True, slots=True)
class TradingDecision:
    """Decisión estructurada emitida por el LLM Decision Agent.

    `confidence` debe estar en [0.0, 1.0]. `fallback_reason` es distinto de
    `None` sólo cuando la decisión es un HOLD de seguridad (fail-safe), p. ej.
    por fallo del proveedor LLM o presupuesto agotado.
    """

    timestamp_ms: int
    action: Action
    confidence: float
    intensity: Intensity = Intensity.MEDIUM
    rationale_summary: str = ""
    supporting_factors: tuple[str, ...] = ()
    risk_factors: tuple[str, ...] = ()
    fallback_reason: str | None = None

    @property
    def is_fallback(self) -> bool:
        """True si la decisión es un HOLD de seguridad (fail-safe)."""
        return self.fallback_reason is not None

    @classmethod
    def hold(cls, timestamp_ms: int, reason: str) -> TradingDecision:
        """Fabrica un HOLD de seguridad con confianza 0.0 y `fallback_reason`."""
        return cls(
            timestamp_ms=timestamp_ms,
            action=Action.HOLD,
            confidence=0.0,
            fallback_reason=reason,
        )

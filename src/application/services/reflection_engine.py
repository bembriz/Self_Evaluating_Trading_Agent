"""Reflection Engine (PRD §35): reflexión estructurada tras cerrar un trade.

Generación determinista por reglas sobre el outcome evaluado. La reflexión
NUNCA modifica automáticamente estrategia ni riesgo (PRD §35-36): solo produce
el registro estructurado para memoria y mejora con aprobación humana.
"""

from __future__ import annotations

import hashlib

from domain.evaluation.outcome import TradeOutcome, TradeResult
from domain.memory.reflection import Reflection, ReflectionResult


class ReflectionEngine:
    """Convierte outcomes evaluados en reflexiones estructuradas."""

    def __init__(
        self,
        *,
        mae_counter_trend_atr: float = 2.5,
        premature_capture_ratio: float = 0.4,
    ) -> None:
        self._mae_counter_trend_atr = mae_counter_trend_atr
        self._premature_capture_ratio = premature_capture_ratio

    def reflect(
        self,
        *,
        outcome: TradeOutcome,
        closed_at_ms: int = 0,
        atr_at_entry: float | None = None,
        captured_pnl: float | None = None,
    ) -> Reflection:
        primary_error, lesson, future_condition = self._classify(
            outcome, atr_at_entry=atr_at_entry, captured_pnl=captured_pnl
        )
        return Reflection(
            id=self._identity(outcome, closed_at_ms),
            outcome_closed_at_ms=closed_at_ms,
            result=_map_result(outcome.result),
            primary_error=primary_error,
            lesson=lesson,
            future_condition=future_condition,
        )

    def _classify(
        self,
        outcome: TradeOutcome,
        *,
        atr_at_entry: float | None,
        captured_pnl: float | None,
    ) -> tuple[str, str, str]:
        if (
            outcome.result is TradeResult.LOSS
            and atr_at_entry
            and atr_at_entry > 0.0
            and outcome.mae >= atr_at_entry * self._mae_counter_trend_atr
        ):
            return (
                "COUNTER_TREND_ENTRY",
                "La entrada fue contra la tendencia dominante y el precio se alejó "
                "más de lo tolerable antes del stop.",
                "Reducir confianza en señales contra el régimen vigente.",
            )
        if (
            outcome.result is TradeResult.WIN
            and captured_pnl is not None
            and outcome.mfe > 0.0
            and captured_pnl < outcome.mfe * self._premature_capture_ratio
        ):
            return (
                "PREMATURE_EXIT",
                "El trade alcanzó una excursión favorable muy superior a la ganancia "
                "capturada antes de la salida.",
                "Evaluar trailing más laxo cuando el régimen acompaña.",
            )
        if outcome.result is TradeResult.BREAKEVEN:
            return (
                "NO_EDGE",
                "El trade cerró sin ventaja clara: la señal no aportó movimiento suficiente.",
                "Exigir confirmación adicional antes de entrar en condiciones similares.",
            )
        if outcome.result is TradeResult.WIN:
            return ("", "Trade dentro de parámetros: entrada, gestión y salida correctas.", "")
        return (
            "STOP_HIT_NORMAL",
            "Pérdida contenida por el stop: riesgo funcionando según diseño.",
            "",
        )

    @staticmethod
    def _identity(outcome: TradeOutcome, closed_at_ms: int) -> str:
        payload = f"{outcome.trade.entry_ts}|{outcome.trade.exit_ts}|{closed_at_ms}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _map_result(result: TradeResult) -> ReflectionResult:
    if result is TradeResult.WIN:
        return ReflectionResult.WIN
    if result is TradeResult.LOSS:
        return ReflectionResult.LOSS
    return ReflectionResult.BREAKEVEN

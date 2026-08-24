"""Reflexión estructurada (PRD §35): lección generada al cerrar un trade.

Solo entra en memoria cuando el outcome está cerrado (`outcome_closed_at_ms`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ReflectionResult(StrEnum):
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"


@dataclass(frozen=True, slots=True)
class Reflection:
    """Reflexión inmutable sobre un trade terminado."""

    id: str
    outcome_closed_at_ms: int
    result: ReflectionResult
    primary_error: str = ""
    lesson: str = ""
    future_condition: str = ""

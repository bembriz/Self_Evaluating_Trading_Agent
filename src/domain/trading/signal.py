"""Señal de trading (PRD §19): decisión + intensidad. Dominio puro."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Action(StrEnum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class Intensity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class Signal:
    timestamp_ms: int
    action: Action
    intensity: Intensity = Intensity.MEDIUM
    reason: str = ""

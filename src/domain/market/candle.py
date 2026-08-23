"""Entidades puras del dominio de mercado (PRD §13, §40). Sin frameworks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

_LABELS = {"15": "15m", "60": "1h", "240": "4h"}


class Timeframe(StrEnum):
    """Intervalo de vela; `value` es el intervalo Bybit REST v5 (minutos)."""

    M15 = "15"
    H1 = "60"
    H4 = "240"

    @property
    def minutes(self) -> int:
        return int(self.value)

    @property
    def label(self) -> str:
        return _LABELS[self.value]

    @classmethod
    def from_label(cls, label: str) -> Timeframe:
        for member in cls:
            if member.label == label:
                return member
        raise ValueError(f"timeframe desconocido: {label}")


@dataclass(frozen=True, slots=True)
class Candle:
    """Vela OHLCV confirmada. `timestamp_ms` es el inicio del intervalo (epoch ms UTC)."""

    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float

    @property
    def timestamp(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp_ms / 1000, tz=UTC)

    def __post_init__(self) -> None:
        if self.high < max(self.open, self.close):
            raise ValueError("high < max(open, close)")
        if self.low > min(self.open, self.close):
            raise ValueError("low > min(open, close)")
        if self.volume < 0:
            raise ValueError("volume negativo")
        if self.turnover < 0:
            raise ValueError("turnover negativo")

"""Decision context: snapshot versionado de lo que vio la estrategia en T.

El ``decision_context`` se persiste como JSONB en cada ``paper_trade_events`` y
permite reconstruir/auditar la decisión sin re-replay del mercado, además de
demostrar no-lookahead (recompute(T) == snapshot(T)).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from domain.market.candle import Candle
from domain.market.indicators import AtrTracker
from domain.market.regime import RegimeClassifier
from domain.trading.strategy import EmaRsiBaseline

SCHEMA_VERSION = 1

_REQUIRED_KEYS = ("schema_version", "signal_reason")


@dataclass(frozen=True, slots=True)
class DecisionContext:
    schema_version: int
    signal_reason: str
    atr: float | None
    ema_fast: float | None
    ema_slow: float | None
    rsi: float | None
    regime: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "signal_reason": self.signal_reason,
            "atr": self.atr,
            "ema_fast": self.ema_fast,
            "ema_slow": self.ema_slow,
            "rsi": self.rsi,
            "regime": self.regime,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionContext:
        validate_decision_context(data)
        return cls(
            schema_version=int(data["schema_version"]),
            signal_reason=str(data["signal_reason"]),
            atr=_optional_float(data.get("atr")),
            ema_fast=_optional_float(data.get("ema_fast")),
            ema_slow=_optional_float(data.get("ema_slow")),
            rsi=_optional_float(data.get("rsi")),
            regime=_optional_str(data.get("regime")),
        )


def validate_decision_context(data: dict[str, Any]) -> None:
    """Valida el esquema versionado; rechaza contextos desconocidos o corruptos."""
    if not isinstance(data, dict):
        raise ValueError("decision_context must be an object")
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"decision_context schema_version inválido: {version!r} != {SCHEMA_VERSION}"
        )
    if "signal_reason" not in data:
        raise ValueError("decision_context sin signal_reason")


def _optional_float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def recompute_decision_contexts(candles: list[Candle]) -> list[DecisionContext]:
    """Recomputa causalmente el ``DecisionContext`` para cada vela (no-lookahead).

    Usa trackers frescos y procesa las velas en orden cronológico; el contexto del
    índice ``T`` depende únicamente de las velas ``<= T`` por construcción.
    """
    strategy = EmaRsiBaseline()
    atr = AtrTracker()
    classifier = RegimeClassifier()
    window: deque[Candle] = deque(maxlen=100)
    results: list[DecisionContext] = []
    for candle in candles:
        window.append(candle)
        regime = classifier.classify(window)
        signal = strategy.on_candle(candle)
        atr_value = atr.update(candle)
        results.append(
            DecisionContext(
                schema_version=SCHEMA_VERSION,
                signal_reason=signal.reason,
                atr=atr_value,
                ema_fast=strategy.ema_fast,
                ema_slow=strategy.ema_slow,
                rsi=strategy.rsi,
                regime=regime.name if regime is not None else None,
            )
        )
    return results

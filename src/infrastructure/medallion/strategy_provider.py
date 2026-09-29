"""StrategyDecisionProvider — adaptador Strategy(on_candle) → DecisionProvider (M9-B).

Puente entre la interfaz de estrategia (`domain.trading.strategy.Strategy`, una
vela confirmada → `Signal`) y el contrato del Trade-Level Replay M7
(`infrastructure.medallion.replay.DecisionProvider`).

Invariantes (FAIL CLOSED):

- Orden estricto: `candle_index` debe ser exactamente el siguiente de la
  secuencia (una llamada por vela, sin huecos, sin repeticiones).
- `decision_ts` DEBE ser el ``close_time`` de la vela (decisión tras cierre
  confirmado); nunca el open_time.
- `Signal.timestamp_ms` DEBE ser el ``open_time`` de la vela: aserción de
  sanidad de la estrategia; JAMÁS se usa como trigger de ejecución
  (`Decision.signal_ts := decision_ts`, close confirmado).
- Acciones: ``HOLD → None``, ``BUY → "buy"``, ``SELL → "sell"``; cualquier otra
  acción aborta la corrida.

El adaptador es genérico sobre ``Strategy`` (Protocol estructural): no importa
ninguna estrategia concreta. Las estrategias preloaded (Donchian/Bollinger)
reciben la secuencia completa de velas en el MISMO orden del replay vía
``rows_to_domain_candles`` (conversión de un solo dueño, valores idénticos a los
del motor: ``timestamp_ms = open_time``, ``turnover = 0.0``).
"""

from __future__ import annotations

from collections.abc import Sequence

from domain.market.candle import Candle
from domain.trading.signal import Action
from domain.trading.strategy import Strategy
from infrastructure.medallion.replay import (
    CandleRow,
    ContextSnapshot,
    Decision,
    ReplayError,
)

__all__ = [
    "StrategyDecisionProvider",
    "rows_to_domain_candles",
]


def rows_to_domain_candles(rows: Sequence[CandleRow]) -> tuple[Candle, ...]:
    """Conversión única CandleRow → Candle: ``timestamp_ms`` = open_time."""
    return tuple(
        Candle(
            timestamp_ms=row.open_time,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
            turnover=0.0,
        )
        for row in rows
    )


class StrategyDecisionProvider:
    """Decide vela a vela con una ``Strategy`` real y las reglas de tiempo de M7."""

    def __init__(self, *, strategy: Strategy, candle_rows: Sequence[CandleRow]) -> None:
        self._strategy = strategy
        self._rows = tuple(candle_rows)
        self._candles = rows_to_domain_candles(self._rows)
        if not self._rows:
            raise ReplayError("strategy provider: sin velas (FAIL CLOSED)")
        self._next_index = 0

    @property
    def candles(self) -> tuple[Candle, ...]:
        """Velas 15m convertidas (misma secuencia que consume la estrategia)."""
        return self._candles

    def decide(
        self,
        *,
        candle_index: int,
        decision_ts: int,
        reference_price: float,
        atr_value: float | None,
        context: ContextSnapshot,
    ) -> Decision | None:
        del context  # las estrategias M9-B son 15m-only; el contexto no influye.
        if candle_index != self._next_index:
            raise ReplayError(
                "strategy provider: candle_index fuera de secuencia "
                f"{candle_index} != esperado {self._next_index} (FAIL CLOSED)"
            )
        if candle_index < 0 or candle_index >= len(self._rows):
            raise ReplayError(
                f"strategy provider: candle_index {candle_index} fuera de rango (FAIL CLOSED)"
            )
        row = self._rows[candle_index]
        if decision_ts != row.close_time:
            raise ReplayError(
                "strategy provider: decision_ts != close_time "
                f"({decision_ts} != {row.close_time}) (FAIL CLOSED)"
            )
        self._next_index += 1

        signal = self._strategy.on_candle(self._candles[candle_index])
        if signal.timestamp_ms != row.open_time:
            raise ReplayError(
                "strategy provider: Signal.timestamp_ms != open_time "
                f"({signal.timestamp_ms} != {row.open_time}) (FAIL CLOSED)"
            )
        if signal.action == Action.HOLD:
            return None
        if signal.action == Action.BUY:
            action = "buy"
        elif signal.action == Action.SELL:
            action = "sell"
        else:
            raise ReplayError(f"strategy provider: acción desconocida {signal.action!r}")
        return Decision(
            action=action,
            signal_ts=decision_ts,
            reference_price=reference_price,
            candle_index=candle_index,
            atr=atr_value,
        )

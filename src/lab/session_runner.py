"""LabSessionRunner: Mode 2 — runtime parity sobre velas congeladas (Fase 17D).

Timing model MVP-A, idéntico a `PaperRunner.handle_kline` (mismo dominio/motor):

- precio = candle.close, atr = None;
- TradingDecision(confidence=1.0, intensity=MEDIUM, rationale=signal.reason);
- equity vía `engine.mark_to_market(candle.close)`.

El runner NO contiene reglas de trading: estrategia, RiskEngine, fills, fees,
slippage y portfolio accounting provienen del runtime existente (Strategy real
+ PaperEngine real). Single-use: una instancia ejecuta una sola sesión.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from application.services.paper_engine import PaperEngine
from domain.trading.decision import TradingDecision
from domain.trading.signal import Intensity
from domain.trading.strategy import Strategy
from lab.experiment_spec import event_trace_hash, metrics_hash
from lab.frozen_dataset import FrozenDatasetAdapter

_HEX64_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class LabCandleEvent:
    """Traza por vela. `action` usa `Action.name` igual que PaperTradeEvent."""

    timestamp_ms: int
    action: str
    filled: bool
    exit_reason: str
    risk_reason: str
    exec_price: float | None
    quantity: float | None
    fee: float
    slippage_cost: float
    equity: float


@dataclass(frozen=True)
class LabSessionResult:
    """Resultado inmutable de una sesión ligado a su ExperimentSpecId."""

    experiment_spec_id: str
    events: tuple[LabCandleEvent, ...]
    metrics: Mapping[str, Any]
    event_trace_hash: str
    metrics_hash_value: str

    def event_trace(self) -> list[dict[str, Any]]:
        """Traza como primitivos canónicos (para hashing/comparación)."""
        return _trace_mapping(self.events)


def _trace_mapping(events: tuple[LabCandleEvent, ...]) -> list[dict[str, Any]]:
    return [
        {
            "timestamp_ms": event.timestamp_ms,
            "action": event.action,
            "filled": event.filled,
            "exit_reason": event.exit_reason,
            "risk_reason": event.risk_reason,
            "exec_price": event.exec_price,
            "quantity": event.quantity,
            "fee": event.fee,
            "slippage_cost": event.slippage_cost,
            "equity": event.equity,
        }
        for event in events
    ]


def summarize_lab_events(
    events: tuple[LabCandleEvent, ...], *, initial_equity: float
) -> dict[str, Any]:
    """Agregados puros sobre la traza (sin estado, determinista)."""
    decisions = {"BUY": 0, "SELL": 0, "HOLD": 0}
    fills = 0
    fees = 0.0
    slippage = 0.0
    risk_rejections = 0
    for event in events:
        decisions[event.action] = decisions.get(event.action, 0) + 1
        if event.filled:
            fills += 1
        fees += event.fee
        slippage += event.slippage_cost
        if event.risk_reason:
            risk_rejections += 1
    final_equity = events[-1].equity if events else initial_equity
    return {
        "candles": len(events),
        "decisions": decisions,
        "fills": fills,
        "fees": fees,
        "slippage_cost": slippage,
        "risk_rejections": risk_rejections,
        "equity_initial": initial_equity,
        "equity_final": final_equity,
    }


class LabSessionRunner:
    """Ejecuta una estrategia real sobre velas congeladas con el PaperEngine real."""

    def __init__(
        self,
        *,
        adapter: FrozenDatasetAdapter,
        strategy: Strategy,
        engine: PaperEngine,
        experiment_spec_id: str,
    ) -> None:
        if _HEX64_RE.fullmatch(experiment_spec_id) is None:
            raise ValueError("experiment_spec_id must be SHA-256 hex")
        self._adapter = adapter
        self._strategy = strategy
        self._engine = engine
        self._spec_id = experiment_spec_id

    def run(self) -> LabSessionResult:
        """Una pasada completa sobre el rango congelado. Determinista."""
        initial_equity = self._engine.portfolio.equity(0.0)
        events: list[LabCandleEvent] = []
        for candle in self._adapter.candles:
            signal = self._strategy.on_candle(candle)
            decision = TradingDecision(
                timestamp_ms=candle.timestamp_ms,
                action=signal.action,
                confidence=1.0,
                intensity=Intensity.MEDIUM,
                rationale_summary=signal.reason,
            )
            paper_event = self._engine.on_price(
                decision=decision,
                price=candle.close,
                atr=None,
                timestamp_ms=candle.timestamp_ms,
            )
            fill = paper_event.fill
            events.append(
                LabCandleEvent(
                    timestamp_ms=candle.timestamp_ms,
                    action=paper_event.action.name,
                    filled=paper_event.filled,
                    exit_reason=paper_event.exit_reason,
                    risk_reason=paper_event.risk_reason,
                    exec_price=fill.exec_price if fill is not None else None,
                    quantity=fill.quantity if fill is not None else None,
                    fee=fill.fee if fill is not None else 0.0,
                    slippage_cost=fill.slippage_cost if fill is not None else 0.0,
                    equity=self._engine.mark_to_market(price=candle.close),
                )
            )
        frozen_events = tuple(events)
        metrics = MappingProxyType(
            summarize_lab_events(frozen_events, initial_equity=initial_equity)
        )
        trace = _trace_mapping(frozen_events)
        return LabSessionResult(
            experiment_spec_id=self._spec_id,
            events=frozen_events,
            metrics=metrics,
            event_trace_hash=event_trace_hash(trace),
            metrics_hash_value=metrics_hash(dict(metrics)),
        )

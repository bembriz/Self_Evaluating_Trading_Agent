"""Log de auditoría en memoria con tope (PRD §53 audit; Fase 13).

Los eventos sensibles (kill switch, cambios de modo, decisiones de riesgo)
quedan registrados para la UI de auditoría. La persistencia durable llega con
la tabla audit_events (§55) en su fase.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Evento auditable inmutable."""

    ts_ms: int
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def now(kind: str, **payload: Any) -> AuditEvent:
        return AuditEvent(ts_ms=int(time.time() * 1000), kind=kind, payload=payload)


class AuditLog:
    """Ring buffer acotado de eventos de auditoría."""

    def __init__(self, maxlen: int = 500) -> None:
        self._events: deque[AuditEvent] = deque(maxlen=maxlen)

    def append(self, event: AuditEvent) -> AuditEvent:
        self._events.append(event)
        return event

    def tail(self, n: int = 50) -> list[AuditEvent]:
        """Últimos `n` eventos, el más reciente primero."""
        items = list(self._events)[-n:]
        return list(reversed(items))

    def __len__(self) -> int:
        return len(self._events)

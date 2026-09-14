"""Logging estructurado JSON a stdout (sin Loki, sin secretos)."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Eventos de ciclo de vida y operación del paper-runner.
PROCESS_START = "PROCESS_START"
PROCESS_STOP = "PROCESS_STOP"
WS_CONNECTED = "WS_CONNECTED"
WS_DISCONNECTED = "WS_DISCONNECTED"
WS_RECONNECTED = "WS_RECONNECTED"
WS_STALE = "WS_STALE"
STATE_RESTORED = "STATE_RESTORED"
BUY_FILL = "BUY_FILL"
SELL_FILL = "SELL_FILL"
IMPORTANT_RISK_REJECTION = "IMPORTANT_RISK_REJECTION"
ERROR = "ERROR"
EXCEPTION = "EXCEPTION"

_IMPORTANT_RISK_REASONS = ("max_daily_loss", "max_drawdown", "kill_switch", "stop_unavailable")


class JsonFormatter(logging.Formatter):
    """Formatea un LogRecord como una línea JSON (timestamp UTC, level, event, campos)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        structured = getattr(record, "structured", None)
        if isinstance(structured, dict):
            payload.update(structured)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class StructuredLogger:
    """Emite eventos estructurados con un contexto fijo (sin secretos)."""

    def __init__(self, logger: logging.Logger, *, context: dict[str, Any] | None = None) -> None:
        self._logger = logger
        self._context = dict(context or {})

    def info(self, event: str, **fields: Any) -> None:
        self._emit(logging.INFO, event, fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._emit(logging.WARNING, event, fields)

    def error(self, event: str, **fields: Any) -> None:
        self._emit(logging.ERROR, event, fields)

    def exception(self, event: str, **fields: Any) -> None:
        self._emit(logging.ERROR, event, fields, exc_info=True)

    def _emit(
        self, level: int, event: str, fields: dict[str, Any], *, exc_info: bool = False
    ) -> None:
        self._logger.log(
            level,
            event,
            extra={"structured": {**self._context, **fields}},
            exc_info=exc_info,
        )


def configure_json_logging() -> logging.Logger:
    """Configura el logger ``seta`` con salida JSON a stdout (sin duplicar handlers)."""
    logger = logging.getLogger("seta")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(isinstance(h.formatter, JsonFormatter) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    return logger


def is_important_risk_rejection(reason: str) -> bool:
    """True si el motivo de rechazo de riesgo merece un evento IMPORTANT_RISK_REJECTION."""
    return reason in _IMPORTANT_RISK_REASONS

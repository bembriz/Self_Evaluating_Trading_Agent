"""Métricas técnicas PRD §62 en formato Prometheus (Fase 13).

Registro propio (no el default global) para tests aislados y para no filtrar
métricas de librerías entre instancias.
"""

from __future__ import annotations

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)


class SetaMetrics:
    """Métricas técnicas del agente: errores, reconexiones, latencias, coste LLM."""

    def __init__(self) -> None:
        self._registry = CollectorRegistry()
        self._errors = Counter(
            "seta_errors_total", "Errores por componente", ["kind"], registry=self._registry
        )
        self._reconnects = Counter(
            "seta_reconnects_total", "Reconexiones WS acumuladas", registry=self._registry
        )
        self._ws_stale = Gauge(
            "seta_ws_stale_status", "1 si el market stream está stale", registry=self._registry
        )
        self._llm_cost = Gauge(
            "seta_llm_cost_usd", "Coste LLM acumulado en USD", registry=self._registry
        )
        self._latency = Histogram(
            "seta_latency_seconds",
            "Latencias por operación",
            ["op"],
            registry=self._registry,
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        )
        self._ws_status = Gauge(
            "seta_ws_status", "1 si el WebSocket está conectado", registry=self._registry
        )
        self._ws_stale_total = Counter(
            "seta_ws_stale_total", "Eventos stale acumulados del stream", registry=self._registry
        )
        self._candles_processed = Counter(
            "seta_candles_processed_total", "Velas confirmadas procesadas", registry=self._registry
        )
        self._atr_ready = Gauge(
            "seta_atr_ready", "1 si ATR completó el warmup", registry=self._registry
        )

    # ------------------------------------------------------------- writers

    def inc_error(self, kind: str) -> None:
        self._errors.labels(kind=kind).inc()

    def inc_reconnect(self) -> None:
        self._reconnects.inc()

    def set_stale_status(self, *, stale: bool) -> None:
        self._ws_stale.set(1.0 if stale else 0.0)

    def set_connected(self, connected: bool) -> None:
        self._ws_status.set(1.0 if connected else 0.0)

    def inc_stale(self) -> None:
        self._ws_stale_total.inc()

    def inc_candle(self) -> None:
        self._candles_processed.inc()

    def set_atr_ready(self, ready: bool) -> None:
        self._atr_ready.set(1.0 if ready else 0.0)

    def set_llm_cost(self, usd: float) -> None:
        self._llm_cost.set(usd)

    def observe_latency(self, op: str, seconds: float) -> None:
        self._latency.labels(op=op).observe(seconds)

    # ------------------------------------------------------------- reader

    def render(self) -> str:
        """Exposición en formato de texto de Prometheus."""
        return generate_latest(self._registry).decode("utf-8")

"""Tracing OpenTelemetry (PRD §61): opt-in por configuración.

Sin `otel_enabled`, no se instala provider ni instrumentación (cero overhead);
con él, FastAPI queda instrumentado con propagación W3C hacia el colector
configurado. Nunca rompe la app si el paquete/colector falta.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def configure_tracing(app: FastAPI, *, enabled: bool, endpoint: str = "") -> bool:
    """Instrumenta la app si está habilitado. Devuelve True si se activó."""
    if not enabled:
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:  # pragma: no cover - entorno sin extras de tracing
        logger.warning("OTel solicitado pero paquetes no disponibles; sin tracing")
        return False

    resource = Resource.create({"service.name": "self-evaluating-trading-agent"})
    provider = TracerProvider(resource=resource)
    if endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    return True

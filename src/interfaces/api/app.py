"""Factory de la aplicación FastAPI (composition root)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from application.services.audit_log import AuditLog
from infrastructure.database.session import build_session_factory, create_engine
from infrastructure.observability.metrics import SetaMetrics
from infrastructure.observability.tracing import configure_tracing
from interfaces.api.routers import dashboard as dashboard_router
from interfaces.api.routers import health, system
from settings import Settings, load_settings


def _mount_static(app: FastAPI) -> None:
    """Sirve assets locales (htmx vendido); sin CDN (PRD §53 seguridad)."""
    from fastapi.staticfiles import StaticFiles

    static_dir = Path(__file__).resolve().parents[1] / "web" / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construye la app; crea el engine en el lifespan y lo inyecta en state."""
    resolved = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(resolved.database_url)
        app.state.session_factory = build_session_factory(engine)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title=resolved.app_name, version=resolved.app_version, lifespan=lifespan)
    app.state.settings = resolved
    app.state.audit_log = AuditLog()
    app.state.metrics = SetaMetrics()
    app.include_router(health.router)
    app.include_router(system.router)
    app.include_router(dashboard_router.router)
    _mount_static(app)
    app.state.otel_enabled = configure_tracing(
        app, enabled=resolved.otel_enabled, endpoint=resolved.otel_endpoint
    )
    return app


app = create_app()

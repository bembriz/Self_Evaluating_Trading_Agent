"""Factory de la aplicación FastAPI (composition root)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from infrastructure.database.session import build_session_factory, create_engine
from interfaces.api.routers import health, system
from settings import Settings, load_settings


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
    app.include_router(health.router)
    app.include_router(system.router)
    return app


app = create_app()

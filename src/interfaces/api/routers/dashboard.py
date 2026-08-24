"""Dashboard de trading (PRD §52-53) + auditoría + /metrics (Fase 13).

Jinja2 con autoescape, actualización por HTMX polling (fragmento /summary),
bind localhost por defecto y rol operator. El estado se lee de SystemState
(clave/valor); claves ausentes se renderizan como "—" hasta que los workers
las publiquen.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from application.services.audit_log import AuditLog

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "web" / "templates"

#: Claves SystemState que alimenta el dashboard (los workers las publican).
STATE_KEYS: tuple[str, ...] = (
    "system:status",
    "bybit:connection",
    "market:prices",
    "orderbook:state",
    "market:health",
    "strategy:active",
    "llm:model",
    "market:regime",
    "decision:latest",
    "position:current",
    "portfolio:pnl",
    "portfolio:drawdown",
    "trades:count",
    "risk:rejected_count",
    "risk:kill_switch",
    "reflections:recent",
    "llm:cost_usd",
    "experiments:list",
    "live:readiness",
)

router = APIRouter()
_templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
# Autoescape explícito (PRD §53): Jinja2Templates no lo expone como kwarg.
_env = _templates.env
_env.autoescape = True
templates = _templates


async def _collect_state(request: Request) -> dict[str, Any]:
    """Lee las claves de estado; la BD caída degrada a valores vacíos."""
    session_factory = getattr(request.app.state, "session_factory", None)
    values: dict[str, Any] = {}
    if session_factory is not None:
        try:
            from infrastructure.database.repositories import (
                SqlAlchemySystemStateRepository,
            )

            async with session_factory() as session:
                repo = SqlAlchemySystemStateRepository(session)
                for key in STATE_KEYS:
                    value = await repo.get(key)
                    if value is not None:
                        values[key] = value
        except Exception:  # noqa: BLE001 - dashboard resiliente sin BD
            values["db"] = {"available": False}
    return values


def _view(state: dict[str, Any]) -> dict[str, Any]:
    """Modelo de vista plano para las plantillas."""
    decision = state.get("decision:latest") or {}
    return {
        "prices": state.get("market:prices") or {},
        "health": state.get("market:health") or {},
        "orderbook": state.get("orderbook:state") or {},
        "bybit": state.get("bybit:connection") or {},
        "strategy": state.get("strategy:active") or {},
        "llm_model": state.get("llm:model") or {},
        "regime": state.get("market:regime") or {},
        "decision": {
            "action": decision.get("action", "—"),
            "confidence": decision.get("confidence", "—"),
            "intensity": decision.get("intensity", "—"),
        },
        "position": state.get("position:current") or {},
        "pnl": state.get("portfolio:pnl") or {},
        "drawdown": state.get("portfolio:drawdown") or {},
        "trades_count": state.get("trades:count") or {},
        "risk_rejected": state.get("risk:rejected_count") or {},
        "kill_switch": state.get("risk:kill_switch") or {"active": "unknown"},
        "reflections": state.get("reflections:recent") or [],
        "llm_cost_usd": state.get("llm:cost_usd") or {},
        "experiments": state.get("experiments:list") or [],
        "live_readiness": state.get("live:readiness") or {"status": "not_evaluated"},
        "db_available": state.get("db", {}).get("available", True),
    }


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> Response:
    view = _view(await _collect_state(request))
    return templates.TemplateResponse(request, "dashboard.html", {"view": view})


@router.get("/dashboard/summary", response_class=HTMLResponse)
async def summary_fragment(request: Request) -> Response:
    """Fragmento que HTMX refresca cada 5s."""
    view = _view(await _collect_state(request))
    return templates.TemplateResponse(request, "summary.html", {"view": view})


@router.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request) -> Response:
    log: AuditLog | None = getattr(request.app.state, "audit_log", None)
    events = log.tail(100) if log is not None else []
    return templates.TemplateResponse(request, "audit.html", {"events": events})


@router.get("/metrics")
async def metrics(request: Request) -> Response:
    from infrastructure.observability.metrics import SetaMetrics

    metrics_registry: SetaMetrics | None = getattr(request.app.state, "metrics", None)
    body = metrics_registry.render() if metrics_registry is not None else ""
    return Response(content=body, media_type="text/plain; version=0.0.4")

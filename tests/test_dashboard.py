"""Tests del dashboard Jinja2+HTMX, auditoría y endpoint /metrics."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from application.services.audit_log import AuditEvent, AuditLog
from interfaces.api.app import create_app
from settings import Settings


@pytest.fixture
def client_no_db() -> Generator[TestClient]:
    """App sin DB disponible: el dashboard debe degradar con elegancia."""
    app = create_app(Settings(postgres_port=1, postgres_password=SecretStr("x")))
    audit = AuditLog()
    audit.append(AuditEvent.now("kill_switch_activated", reason="test"))
    app.state.audit_log = audit
    with TestClient(app) as c:
        yield c


def test_dashboard_and_summary_render(client_no_db: TestClient) -> None:
    page = client_no_db.get("/dashboard")
    assert page.status_code == 200
    assert "htmx" in page.text.lower()
    frag = client_no_db.get("/dashboard/summary")
    assert frag.status_code == 200
    body = frag.text
    for marker in (
        "ETH",
        "BTC",
        "Régimen",
        "confianza",
        "Kill switch",
        "LIVE readiness",
        "Costos LLM",
    ):
        assert marker.lower() in body.lower(), marker


def test_summary_fragment_for_htmx_polling(client_no_db: TestClient) -> None:
    r = client_no_db.get("/dashboard/summary")
    assert r.status_code == 200
    assert 'hx-get="/dashboard/summary"' in client_no_db.get("/dashboard").text


def test_metrics_endpoint_exposes_registry(client_no_db: TestClient) -> None:
    r = client_no_db.get("/metrics")
    assert r.status_code == 200
    assert "seta_" in r.text and "# TYPE" in r.text


def test_audit_ui_lists_events(client_no_db: TestClient) -> None:
    r = client_no_db.get("/audit")
    assert r.status_code == 200
    assert "kill_switch_activated" in r.text


def test_tracing_disabled_by_default(client_no_db: TestClient) -> None:
    from typing import cast

    from fastapi import FastAPI

    app = cast(FastAPI, client_no_db.app)
    assert app.state.otel_enabled is False

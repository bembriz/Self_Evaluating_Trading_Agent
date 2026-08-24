# UAT — Fase 13: Dashboard & Observability

> Prueba de aceptación de usuario (HITL). El agente NO puede aprobar UAT.

## Pasos

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | `uv run pytest tests --ignore=tests/integration --cov=src --cov-branch --cov-fail-under=90` | `362 passed, 1 skipped`; cobertura >= 90% (93.56%) |
| 2 | `uv run pytest tests/test_dashboard.py tests/test_metrics_registry.py -v` | Dashboard y fragmento HTMX renderizan elementos §52; /metrics expone seta_*; auditoría lista eventos; tracing off por defecto |
| 3 | `uv run uvicorn interfaces.api.app:app --port 8000` y abrir http://localhost:8000/dashboard | Página visible; fragmento se refresca cada 5s; /audit y /metrics navegables |
| 4 | `python3 harness/scripts/gate_check.py --phase 13` | `5 PASS · 0 FAIL · 2 MANUAL` |
| 5 | (Pendiente de entorno) Con Docker: `docker compose up -d prometheus grafana` | Prometheus scrapea /metrics; dashboard SETA en Grafana (localhost:3000) |

## Resultado observado

| Paso | Resultado observado | ¿Coincide? (SÍ/NO) | Notas |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |

---

## VEREDICTO UAT: APPROVED
Decisor: usuario (sesión opencode)  Fecha: 2026-08-24
Comentario:
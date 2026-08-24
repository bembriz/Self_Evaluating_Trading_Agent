# UAT — Fase 10: Risk & Paper Execution

> Prueba de aceptación de usuario (HITL). El agente NO puede aprobar UAT.

## Precondiciones

| # | Precondición | Verificada ☐ |
|---|---|---|
| 1 | Cambios de la fase en working tree (rama `feature/phase-08-llm-decision-agent`) | ☐ |
| 2 | `uv sync` ejecutado | ☐ |

## Pasos

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | `uv run pytest tests --ignore=tests/integration --cov=src --cov-branch --cov-fail-under=90` | `309 passed, 1 skipped`; cobertura ≥ 90% (93.10%) |
| 2 | `uv run pytest tests/test_risk_engine.py tests/test_risk_sizing.py tests/test_risk_guards.py tests/test_risk_stops.py --cov=domain.risk --cov-branch --cov-report=term` | Todos PASS; TOTAL **100%** en statements y branch |
| 3 | `uv run pytest tests/test_paper_engine.py -v` | Todos PASS: stop sale aunque el LLM diga HOLD; TP y trailing operativos; determinismo idéntico en doble ejecución; fees+slippage descontados del PnL neto |
| 4 | `python3 harness/scripts/gate_check.py --phase 10` | `5 PASS · 0 FAIL · 2 MANUAL` |
| 5 | Revisar `docs/phases/phase-10-report.md` | Coherente con lo observado |

## Resultado observado

| Paso | Resultado observado | ¿Coincide? (SÍ/NO) | Notas |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |

## Incidencias encontradas

> Nota conocida: tests de integración requieren Docker/PostgreSQL (no disponible aquí).

---

## VEREDICTO UAT: APPROVED
<!-- Sustituir PENDING por APPROVED o REJECTED -->
Decisor: usuario (sesión opencode)  Fecha: 2026-08-23
Comentario:
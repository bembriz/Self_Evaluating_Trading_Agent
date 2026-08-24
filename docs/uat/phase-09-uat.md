# UAT — Fase 09: Trading Memory / RAG

> Prueba de aceptación de usuario (HITL). El agente NO puede aprobar UAT.

## Precondiciones

| # | Precondición | Verificada ☐ |
|---|---|---|
| 1 | Cambios de la fase en working tree (rama `feature/phase-08-llm-decision-agent`) | ☐ |
| 2 | `uv sync` ejecutado (incluye DP-003: pgvector + fastembed) | ☐ |

## Pasos

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | `uv run pytest tests --ignore=tests/integration --cov=src --cov-branch --cov-fail-under=90` | `254 passed, 1 skipped`; `Total coverage: 92.28%` |
| 2 | `uv run pytest tests/test_memory_domain.py tests/test_memory_comparison.py -v` | Todos PASS: filtro temporal estricto (`outcome < decision`), guard lanza `MemoryLeakageError`, comparador con ambos brazos |
| 3 | `RUN_MODEL_SMOKE=1 uv run pytest tests/test_fastembed_provider.py::test_smoke_real_model_downloads_and_embeds -v` | PASS: modelo local descarga y genera vector de 384 dims (~10s; requiere red la primera vez) |
| 4 | `python3 harness/scripts/gate_check.py --phase 09` | `5 PASS · 0 FAIL · 2 MANUAL` |
| 5 | Revisar `docs/phases/09/dp-003-pgvector-fastembed.md` y `docs/phases/phase-09-report.md` | Coherentes; desviación de modelo documentada |

## Resultado observado

| Paso | Resultado observado | ¿Coincide? (SÍ/NO) | Notas |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |

## Incidencias encontradas

> Nota conocida: tests de integración pgvector requieren Docker/PostgreSQL (no disponible aquí).

---

## VEREDICTO UAT: APPROVED
<!-- Sustituir PENDING por APPROVED o REJECTED -->
Decisor: usuario (sesión opencode)  Fecha: 2026-08-23
Comentario:

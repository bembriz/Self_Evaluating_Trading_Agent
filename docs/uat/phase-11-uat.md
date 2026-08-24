# UAT — Fase 11: Evaluation & Reflection

> Prueba de aceptación de usuario (HITL). El agente NO puede aprobar UAT.

## Pasos

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | `uv run pytest tests --ignore=tests/integration --cov=src --cov-branch --cov-fail-under=90` | `330 passed, 1 skipped`; cobertura ≥ 90% (93.25%) |
| 2 | `uv run pytest tests/test_outcome_evaluator.py tests/test_reflection_engine.py -v` | MFE/MAE correctos (nunca negativos); clasificación WIN/LOSS/BREAKEVEN; errores COUNTER_TREND_ENTRY / PREMATURE_EXIT / NO_EDGE según caso |
| 3 | `uv run pytest tests/test_memory_writer.py tests/test_improvement_proposals.py -v` | Reflexión de trade no cerrado → ValueError; leakage → MemoryLeakageError; approve por "llm" → PermissionError; propuesta aprobada NO muta configuración |
| 4 | `python3 harness/scripts/gate_check.py --phase 11` | `5 PASS · 0 FAIL · 2 MANUAL` |

## Resultado observado

| Paso | Resultado observado | ¿Coincide? (SÍ/NO) | Notas |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |

---

## VEREDICTO UAT: APPROVED
Decisor: usuario (sesión opencode)  Fecha: 2026-08-23
Comentario:
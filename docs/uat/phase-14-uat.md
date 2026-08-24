# UAT — Fase 14: Robustness Evaluation

> Prueba de aceptación de usuario (HITL). El agente NO puede aprobar UAT.

## Pasos

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | `uv run pytest tests --ignore=tests/integration --cov=src --cov-branch --cov-fail-under=90` | `380 passed, 1 skipped`; cobertura >= 90% (93.69%) |
| 2 | `uv run pytest tests/test_bootstrap.py tests/test_sensitivity.py tests/test_comparison.py -v` | IC contiene a la media; determinismo con seed; Monte Carlo p50<=p95<=p99 y ruina=100% con pérdidas totales; fees/slippage degradan monótonamente; pico estrecho rechazado (is_robust=False); regla 2 regímenes; baselines PASS/FAIL correctos; overfit detectado |
| 3 | `python3 harness/scripts/gate_check.py --phase 14` | `5 PASS · 0 FAIL · 2 MANUAL` |

## Resultado observado

| Paso | Resultado observado | ¿Coincide? (SÍ/NO) | Notas |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |

---

## VEREDICTO UAT: APPROVED
Decisor: usuario (sesión opencode)  Fecha: 2026-08-24
Comentario:
# UAT — Fase 12: Bybit Testnet

> Prueba de aceptación de usuario (HITL). El agente NO puede aprobar UAT.

## Pasos

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | `uv run pytest tests --ignore=tests/integration --cov=src --cov-branch --cov-fail-under=90` | `353 passed, 1 skipped`; cobertura ≥ 90% (93.35%) |
| 2 | `uv run pytest tests/test_bybit_trade_auth.py tests/test_bybit_trade_client.py tests/test_bybit_recovery.py -v` | Firma HMAC determinista y sensible a cada campo; órdenes crear/cancelar idempotente; retCode→error; 429 reintenta; reconciliación detecta unknown/stale/diffs; supervisor recupera y agota con techo |
| 3 | `python3 harness/scripts/gate_check.py --phase 12` | `5 PASS · 0 FAIL · 2 MANUAL` |
| 4 | (OPCIONAL, requiere BYBIT_API_KEY/BYBIT_API_SECRET testnet en .env) Colocar una orden Market mínima en ETHUSDT testnet vía un script propio | Orden aceptada por Testnet; visible en la UI de Bybit Testnet |

> El Paso 4 es el único que toca el exchange real: manual, controlado y fuera de CI.

## Resultado observado

| Paso | Resultado observado | ¿Coincide? (SÍ/NO) | Notas |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |

---

## VEREDICTO UAT: APPROVED
Decisor: usuario (sesión opencode)  Fecha: 2026-08-24
Comentario:
# UAT — Fase 15: Local Release Candidate

> Prueba de aceptación de usuario (HITL). El agente NO puede aprobar UAT.

## Estado honesto

El veredicto binario actual es **NOT_ACCEPTED**: 3 gates PASS (OBSERVABILITY, SECURITY, CI-local),
4 PENDING por recursos externos (corridas oficiales backtest/replay/paper, claves Testnet) y el UAT humano.

## Pasos

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | Revisar `docs/phases/15/LOCAL_RELEASE_REPORT.md` | Tabla binaria de los 8 gates coherente |
| 2 | `python3 harness/scripts/release_check.py` | Mismo veredicto reproducible |
| 3 | Decidir: (a) aportar recursos para completar gates pendientes, o (b) aceptar fase bloqueada-pendiente-recursos y registrar decisión |

## Resultado observado

| Paso | Resultado observado | ¿Coincide? (SÍ/NO) |
|---|---|---|
| 1 | | |
| 2 | | |
| 3 | | |

---

## VEREDICTO UAT: PENDING
Decisor: ________________  Fecha: ________
Comentario:
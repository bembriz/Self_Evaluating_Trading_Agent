# UAT — Fase 15: Local Release Candidate

> Prueba de aceptación de usuario (HITL). El agente NO puede aprobar UAT.

## Estado honesto

El veredicto binario actual queda pendiente solo de la aprobación formal del gate de fase:
los 8 gates del Local Release Candidate tienen evidencia PASS tras la validación Testnet real.

## Pasos

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | Revisar `docs/phases/15/LOCAL_RELEASE_REPORT.md` | Tabla binaria de los 8 gates coherente |
| 2 | `python3 harness/scripts/release_check.py` | Mismo veredicto reproducible |
| 3 | Decidir: (a) aportar recursos para completar gates pendientes, o (b) aceptar fase bloqueada-pendiente-recursos y registrar decisión |

## Resultado observado

| Paso | Resultado observado | ¿Coincide? (SÍ/NO) |
|---|---|---|
| 1 | Reporte revisado tras evidencia Testnet | SÍ |
| 2 | `release_check.py` reproducido con gates PASS | SÍ |
| 3 | Usuario declaró `uat validado` en sesión OpenCode | SÍ |

---

## VEREDICTO UAT: APPROVED
Decisor: usuario  Fecha: 2026-09-01
Comentario: UAT validado por declaración explícita en sesión OpenCode.

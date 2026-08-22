---
name: release-readiness
description: Usar al evaluar si una versión local está lista para cierre (Fase 15), consolidar gates BACKTEST/REPLAY/PAPER/TESTNET/OBSERVABILITY/SECURITY/CI/UAT, o preparar LOCAL_RELEASE_REPORT
---

# release-readiness — Cierre de Local Release Candidate

## Propósito

Decidir con evidencia si el sistema alcanza `LOCAL V1 = ACCEPTED`: los 8 gates del PRD §15 en PASS simultáneo, reporte de release MD+PDF y aprobación humana.

## Cuándo usar

- Fase 15 (Local Release Candidate).
- Re-evaluación tras cambios mayores post-release.
- Preparación del paquete de revisión para el usuario.

**Cuándo NO:** gates parciales de fases intermedias (usa reporting-fases normal).

## Los 8 gates obligatorios (PRD §15)

| Gate | Evidencia mínima |
|---|---|
| BACKTEST | corrida completa sobre dataset congelado + métricas §45 |
| REPLAY | replay determinista reproducible (mismo hash → mismo resultado) |
| PAPER | paper trading operativo con fees/slippage/coste LLM |
| TESTNET | lifecycle órdenes validado (Fase 12) |
| OBSERVABILITY | métricas técnicas expuestas y consultables |
| SECURITY | sin secretos, endpoints protegidos, audit trail |
| CI | pipeline verde completo |
| UAT | checklist HITL APPROVED |

## Checklist de preparación

1. Todos los gates de fases previas APPROVED en ledger (sin excepciones).
2. Dataset oficial congelado verificado por SHA-256 antes de cada corrida.
3. Comparativa completa: Buy&Hold vs baseline determinista vs ML vs LLM(+memoria) — Net PnL, no bruto.
4. `LOCAL_RELEASE_REPORT.md` generado desde reporting-fases + PDF.
5. Rollback documentado (tag/versión anterior operativa).
6. Presentación al usuario → decisión ACCEPTED / NOT_ACCEPTED.

## Errores comunes

- Declarar readiness con algún gate "casi": prohibido, es binario.
- Olvidar coste LLM en las comparativas (Fully Loaded PnL).
- Congelar dataset después de correr experimentos (orden correcto: congelar→correr).

## Referencias

- PRD §15, §45–48. Skills: reporting-fases, uat-hitl, walk-forward-validacion, risk-engine.

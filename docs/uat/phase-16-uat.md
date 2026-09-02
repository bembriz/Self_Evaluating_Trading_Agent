# UAT — Fase 16: Paper Trading Certification

> Prueba de aceptación de usuario (HITL). El agente NO puede aprobar UAT.
> Ejecuta los pasos tal cual y completa "Resultado observado" y el veredicto final.

## Precondiciones

| # | Precondición | Verificada ☐ |
|---|---|---|
| 1 | Repositorio en la rama de trabajo de Fase 16. | |
| 2 | Entorno Python/uv existente del proyecto disponible; no instalar dependencias nuevas. | |
| 3 | Archivos presentes: `harness/scripts/paper_certification.py`, `docs/phases/16/certification-state.json`, `docs/phases/16/PAPER_CERTIFICATION_REPORT.md`. | |
| 4 | No existe decisión de habilitar LIVE durante esta UAT. | |

## Entradas / Datos

- Estado: `docs/phases/16/certification-state.json`.
- Reporte de certificación: `docs/phases/16/PAPER_CERTIFICATION_REPORT.md`.
- Evidencia: `docs/phases/16/evidence/`.
- Ledger: `harness/state/progress.yaml` consultado mediante `python3 harness/scripts/progress.py report`.

## Pasos

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | `uv run pytest harness/tests/test_paper_certification.py -q` | La suite termina con 9 tests PASS y exit 0. |
| 2 | `python3 harness/scripts/paper_certification.py --state docs/phases/16/certification-state.json --report docs/phases/16/PAPER_CERTIFICATION_REPORT.md` | El comando termina con exit 0 y el reporte mantiene `Status: PENDING` mientras no existan 30 días, 200 trades y 2 regímenes reales. |
| 3 | `python3 harness/scripts/progress.py report` | Fase 16 aparece `in_progress`, con 2/5 done y 3 bloqueados. |
| 4 | `python3 harness/scripts/gate_check.py --phase 16` | El gate falla por `scope-complete` con pendientes/bloqueados: `certificacion-30-dias`, `certificacion-200-trades`, `certificacion-2-regimenes`; no debe pasar el gate todavía. |
| 5 | Revisar `docs/phases/16/evidence/strategy-hash.log` | Existen hashes de estrategia/riesgo/config paper usados para inmutabilidad; no hay secretos expuestos. |

## Baseline Runner Manual Checks

| Step | Command | Expected |
|---|---|---|
| 1 | `docker compose config` | Shows `paper-runner` with `restart: unless-stopped`, no `ports`, `TRADING_MODE=paper`, `LIVE_TRADING_ENABLED=false`. |
| 2 | After DP-004 approval only: `docker compose up -d postgres paper-runner` | Service starts and remains running. |
| 3 | `docker compose logs --tail=100 paper-runner` | Logs show Bybit kline processing and paper events, no LIVE order placement. |
| 4 | Tras rebuild: `docker compose logs --tail=100 paper-runner` y `ls reports/paper/` | Logs muestran klines procesados; existe al menos un `paper-*.md` tras el primer intervalo. |

## Evidencia a adjuntar

- Salida de cada comando ejecutado en los pasos 1 a 4.
- Confirmación visual de `Status: PENDING` en `docs/phases/16/PAPER_CERTIFICATION_REPORT.md`.
- Confirmación visual de que no se habilitó LIVE ni se generaron trades artificiales.

## Resultado observado

| Paso | Resultado observado | ¿Coincide? (SÍ/NO) | Notas |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |

## Incidencias encontradas

> Desviaciones, errores o comportamientos inesperados.

---

## VEREDICTO UAT: PENDING
<!-- Sustituir PENDING por APPROVED o REJECTED. gate_check exige el veredicto APPROVED visible (los comentarios HTML no cuentan) al check uat-approved -->
Decisor: ________________  Fecha: ________
Comentario:

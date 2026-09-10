# Commit Candidate Report — 2026-09-08 · Fase 16c.3 (Persistent observability)

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

Logging estructurado JSON a stdout (sin Loki) para el paper-runner + preparación de Prometheus (retention ≥45d, volumen persistente, red interna, sin exposición pública). No cambia estrategia, risk, fees/slippage ni comportamiento de trading. Prometheus **no se despliega** (preflight adjunto).

## Rama

| Campo | Valor |
|---|---|
| branch | `fix/phase-16c-restart-safe` |
| base commit | `1b62354` (16c.2 decision_context) |

## Archivos

- **Creados:**
  - `src/infrastructure/observability/logging.py`
  - `tests/test_json_logging.py`, `tests/test_cli_logging.py`, `tests/test_prometheus_config.py`
  - `docs/phases/16c/prometheus-production-preflight.md`
  - `docs/phases/16c/post-commit-verification-002.md` (doc de cierre 16c.2)
  - `docs/phases/16c/commit-candidate-003.md` (este reporte, incluido en el commit)
- **Modificados:**
  - `src/interfaces/cli/paper_runner.py` (wiring de eventos de logging en `_run`/`_run_loop`)
  - `compose.yaml` (retention 45d en prometheus)
- **Eliminados:** ninguno

## Diff

`git diff --cached --stat`: **9 files changed, 937 insertions(+), 12 deletions(-)**.

## Arquitectura afectada

- `StructuredLogger`/`JsonFormatter`/`configure_json_logging` (nuevo, infrastructure/observability).
- `paper_runner` CLI: emite `PROCESS_START/STOP`, `WS_*`, `STATE_RESTORED`, `BUY_FILL/SELL_FILL`, `IMPORTANT_RISK_REJECTION`, `EXCEPTION`. No loguea HOLD.
- `compose.yaml`: solo añade `command` de retention a prometheus (sin cambios en paper-runner).

## Índice del grafo

- [x] re-index: 2741 nodos / 12014 edges · 0 skipped/parse_partial
- [x] `detect_changes` since `1b62354`: 8 changed_files · 75 seed_symbols · 51 impacted
- [x] `check_index_coverage` (logging.py, paper_runner.py, compose.yaml): `no_recorded_issue`

## Tests ejecutados

| Suite | Resultado |
|---|---|
| Total | **576 passed, 1 skipped** |
| Cobertura branch | **92%** (`logging.py` 98%) |

### Rutas de error críticas (nivel ERROR, no silenciosas)

| Ruta | Evento | Level | Test | Resultado |
|---|---|---|---|---|
| WS error (`WebSocketDisconnected`) | `WS_DISCONNECTED` + reason | ERROR | `test_run_loop_logs_ws_disconnect_and_reconnect` | PASS |
| recovery error (`RecoveryDivergenceError`/`GapError`) | `EXCEPTION` + traceback | ERROR | `test_restore_error_logged_as_exception` | PASS |
| DB/commit error | `EXCEPTION` + traceback | ERROR | `test_run_loop_logs_commit_error_as_exception` | PASS |
| unexpected exception (`handle_kline`) | `EXCEPTION` + traceback | ERROR | `test_run_loop_logs_exception_and_propagates` | PASS |
| EXCEPTION método | `EXCEPTION` | ERROR | `test_json_logger_exception` | PASS |

### Tests mínimos obligatorios (nombre → PASS)

| Requisito | Test | Resultado |
|---|---|---|
| JSON log válido | `test_json_logger_emits_valid_json` | PASS |
| PROCESS_START emitted | `test_json_logger_emits_valid_json` (event=PROCESS_START) | PASS |
| WS reconnect logged | `test_run_loop_logs_ws_disconnect_and_reconnect` | PASS |
| fill logged | `test_run_loop_logs_buy_fill` + `test_run_loop_logs_sell_fill` | PASS |
| important risk rejection logged | `test_run_loop_logs_important_risk_rejection` | PASS |
| exception logged | `test_run_loop_logs_exception_and_propagates` + `test_json_logger_exception` | PASS |
| no secrets in logs | `test_json_logger_no_secrets_in_logs` | PASS |
| Prometheus scrape paper-runner PASS | `test_prometheus_scrapes_paper_runner` | PASS |
| metrics survive Prometheus restart | `test_prometheus_has_persistent_tsdb_volume` | PASS |
| retention configured >=45d | `test_prometheus_retention_at_least_45d` | PASS |
| paper-runner continúa si Prometheus cae | `test_paper_runner_does_not_depend_on_prometheus` | PASS |
| port no expuesto públicamente | `test_paper_runner_metrics_port_not_published_publicly` + `test_prometheus_port_loopback_only` | PASS |

Métricas existentes (`seta_ws_status`, `seta_reconnects_total`, `seta_errors_total{kind="ws"}`, `seta_ws_stale_total`, `seta_candles_processed_total`, `seta_atr_ready`) siguen disponibles (sin cambios en `SetaMetrics`).

## Calidad

```bash
uv run ruff check .             # All checks passed
uv run ruff format --check .    # 258 files already formatted
uv run mypy src tests           # Success: no issues found in 227 source files
uv run pytest                   # 576 passed, 1 skipped
```

## Seguridad

- [x] Secret scan: 0 coincidencias reales (solo docstrings "sin secretos" y el test anti-secretos)
- [x] Sin secretos ni credenciales en el contexto del logger
- [x] Sin cambios en `LIVE_TRADING_ENABLED`, fees, slippage, thresholds

## Riesgos

- `configure_json_logging` es idempotente (no duplica handlers). Logging es aditivo; no altera el flujo de trading.
- Prometheus es opt-in (no desplegado). El runner no depende de él.

## Deuda técnica

- Prometheus aún no desplegado en lenovosrv (preflight adjunto, pendiente GATE de infraestructura).
- `application_version` sin bump (política B); `0.2.0` antes del redeploy integrado de 16c.

## Versionado

`strategy_version = baseline-v1` · `risk_config_version = risk-v1` · `application_version` sin bump.

## Mensaje de commit propuesto

```
feat(phase-16c): structured JSON logging + prometheus config

- logging JSON a stdout (sin Loki): PROCESS_START/STOP, WS_*, STATE_RESTORED,
  BUY_FILL/SELL_FILL, IMPORTANT_RISK_REJECTION, EXCEPTION (no HOLD)
- StructuredLogger con contexto fijo (session/symbol/timeframe/versions), sin secretos
- compose.yaml: prometheus retention >=45d + volumen persistente (sin despliegue)
- strategy_version/risk_config_version sin cambios
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

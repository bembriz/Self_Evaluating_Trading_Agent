# Commit Candidate Report — Observabilidad mínima paper-runner (Fase 16b, Opción A)

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

Cubrir el único gap crítico de observabilidad detectado en el UAT 16b: **estado y reconexiones del WebSocket Bybit** durante los 30 días de Paper Certification. Instrumentar el `paper-runner` reutilizando `SetaMetrics` y `prometheus-client` existentes (sin dependencias nuevas) y exponer `/metrics` en `127.0.0.1` (sin exposición pública). No se despliegan Prometheus/Grafana.

## Rama

| Campo | Valor |
|---|---|
| branch | `fix/phase-16b-paper-runner-atr` |
| base commit | `3549194` |

## Archivos

- **Creados:**
  - `src/infrastructure/observability/server.py` (servidor `/metrics` stdlib en loopback)
  - `tests/test_observability_metrics.py`, `tests/test_observability_server.py`, `tests/e2e/test_e2e_ws_observability.py`
  - `docs/phases/16b/observability-minimal-proposal.md`
- **Modificados:**
  - `src/infrastructure/observability/metrics.py` (métricas nuevas + renombrado `seta_ws_stale`→`seta_ws_stale_status`)
  - `src/interfaces/cli/paper_runner.py` (wiring + detección de stale vía `wait_for`)
  - `src/application/services/paper_runner.py` (`atr_ready`)
  - `src/settings.py` (`paper_metrics_port`)
  - `src/version.py` (`0.1.1 → 0.1.2`)
  - `tests/test_metrics_registry.py`, `tests/test_paper_runner.py`

## Métricas cubiertas

| Requisito | Métrica Prometheus | Tipo |
|---|---|---|
| ws_status | `seta_ws_status` | Gauge (1 conectado / 0) |
| reconnect_total | `seta_reconnects_total` | Counter (reutilizada) |
| ws_errors_total | `seta_errors_total{kind="ws"}` | Counter (reutilizada) |
| ws_stale_total | `seta_ws_stale_total` | Counter (nueva) |
| candles_processed | `seta_candles_processed_total` | Counter (nueva) |
| atr_ready | `seta_atr_ready` | Gauge (nueva) |

Se conserva `seta_ws_stale` renombrado a `seta_ws_stale_status` (gauge de status) para evitar colisión de nombre con el contador.

## Tests ejecutados

| Suite | Resultado |
|---|---|
| Suite completa `tests/` (unit+integration+e2e) | **499 passed, 1 skipped** |
| E2E WS (connect→disconnect→reconnect→métricas + stale) | PASS |
| `/metrics` servido (loopback, port 0) | PASS |
| Unit métricas (`test_observability_metrics.py`, `test_metrics_registry.py`) | PASS |
| `atr_ready` (warmup 15 velas) | PASS |
| Test skipped | `test_fastembed_provider.py:97` (requiere `RUN_MODEL_SMOKE=1`) |

## Cobertura / Calidad

- Cobertura global: **94.42%** (branch 94%) — umbral 90% superado.
- `ruff check` / `ruff format --check`: limpios.
- `mypy src tests`: 0 issues (212 ficheros).

## Seguridad

- Sin secretos en el diff. `/metrics` bind a `127.0.0.1` (no público).

## Riesgos

- La detección de stale introduce `asyncio.wait_for(recv, timeout)`; ante un stream que legítimamente no emite mensajes durante `stale_timeout_seconds` (10s), se fuerza una reconexión. Con klines 15m el stream emite actualizaciones por segundo, por lo que el timeout es seguro.
- `/metrics` en `127.0.0.1:9090` (configurable `PAPER_METRICS_PORT`); sin auth (loopback-only, consistente con R1.5).

## Rollback

`git revert <commit>` (dominio/observabilidad; sin migraciones ni schema).

## Mensaje de commit propuesto

```
feat(observability): instrumentar paper-runner con SetaMetrics + /metrics en loopback

- SetaMetrics: nuevas ws_status, ws_stale_total, candles_processed_total, atr_ready
  (y renombra seta_ws_stale -> seta_ws_stale_status); reutiliza reconnects/errors
- server.py: /metrics (stdlib http.server) en 127.0.0.1, sin exposición pública
- paper_runner: emite ws_status/reconnect/error/stale/velas/atr_ready; detección de
  stale vía asyncio.wait_for -> reconexión
- version 0.1.1 -> 0.1.2 (strategy_version=baseline-v1, risk-v1 sin cambios)
- tests: métricas, servidor /metrics, E2E disconnect/reconnect/stale, atr_ready
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

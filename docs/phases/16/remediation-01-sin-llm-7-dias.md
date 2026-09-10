# Remediación 1 — Trading sin LLM durante 7 días (no-LLM)

- **Fecha:** 2026-09-02
- **Origen:** `docs/audits/2026-09-02-auditoria-lenosrv-vs-prd-3-1.md` (gaps G1–G5, S1).
- **Objetivo:** dejar operativo en `lenovosrv` un **paper trading determinista estable por 7 días** (fuente `baseline-v1`, sin LLM), con regímenes confirmados, reportes periódicos, estado de certificación persistente y observabilidad. Cierre a los 7 días = gate de entrada a la Remediación 2.
- **Decisiones de alcance aprobadas:** mantener `baseline-v1` · solo observabilidad (sin dashboard/API) · G6 (BTC/multi-TF/orderbook) → Remediación 2 · deploy vía rsync del commit aprobado + `docker compose up --build`.

---

## Criterio de éxito (día 7)

1. Proceso estable: sin reinicios forzados por crash WS; warmup de 50 velas completado.
2. Trades reales del baseline tras warmup (BUY/SELL con fills y equity ≠ 1000) — sin garantía de densidad, por diseño determinista.
3. ≥1 régimen confirmado con evidencia estructurada (idealmente ≥2 para acercar `certificacion-2-regimenes`).
4. Reportes periódicos (`reports/paper/`) y `certification-state.json` actualizándose.
5. Métricas visibles en Prometheus/Grafana (reconnects, errores, stale, velas, latencias).

---

## Tareas

### R1.0 — Gobernanza (gate previo)
- Preparar **Commit Candidate Report** (plantilla `harness/templates/commit-candidate.md`) del diff pendiente en la rama `feature/paper-regime-certification`: `regime_confirmation.py`, integración de regímenes en `PaperRunner`/CLI, fixtures pgvector, evidencia, DP-005.
- Obtener **autorización explícita de commit** → ejecutar commit.
- Blast radius con `detect_changes` + `check_index_coverage` antes del reporte.

### R1.1 — Redespliegue con la imagen actual (G2)
- Desde el commit aprobado: rsync a `/srv/docker/self-evaluating-trading-agent/` excluyendo `.venv`, `datasets`, `.git`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `.coverage`.
- `docker compose up --build -d postgres paper-runner`.
- Verificar en el contenedor que `/app/src/application/services/regime_confirmation.py` existe y que las migraciones están al nivel de la DB.
- **Evidencia:** `evidence.sh` → `deploy-applied-lenosrv-r1.log`, `docker exec ls`.

### R1.2 — Resiliencia WS sin reset de estado (G5) [crítico]
- En `src/interfaces/cli/paper_runner.py` (`_run_loop`): ante `WebSocketDisconnected`/`ConnectionClosed`, **reconectar el WS con backoff (patrón `ConnectionSupervisor`) y re-suscribir klines reutilizando el MISMO `PaperRunner`** (warmup EMA/engine/trackers de régimen intactos).
- Añadir límite de reintentos + log estructurado + métricas (`inc_reconnect`, `inc_error`).
- **TDD:** test con stream fake que corta la conexión y verifica continuidad de procesamiento y conservación del estado entre reconexiones.
- **Evidencia:** tests unit/integration, `paper-runner-resilience-*.log`.

### R1.3 — Reportes periódicos y estado (G4)
- Configurar `PAPER_REPORT_INTERVAL_HOURS` (~6 h) en el compose/env del server.
- Verificar que los volúmenes host `reports/` y `certification/` son escribibles por el UID del contenedor (ajustar permisos del dir en el server si hace falta).
- Confirmar el primer reporte MD + `certification-state.json`.
- Marcar entregable `informes-periodicos` en el ledger (`progress.py mark-done`).
- **Evidencia:** `compose-config-reports-r1.log`, primer reporte + state.

### R1.4 — Verificación del brazo determinista (G3)
- Tras ~1 día (warmup completado), verificar en DB que `paper_trade_events` ya no es 100% HOLD: aparecen BUY/SELL, fills, fees/slippage y equity móvil.
- No cambiar estrategia (`baseline-v1`).
- **Evidencia:** query `SELECT action, count(*) ...` + rango temporal.

### R1.5 — Observabilidad (G1)
- Instrumentar `paper-runner` con `SetaMetrics` y exponer `/metrics` (Prometheus format) mediante `http.server` de stdlib en `127.0.0.1` (sin dependencias nuevas → sin Dependency Proposal).
- Desplegar servicios `prometheus` y `grafana` del compose en `lenovosrv`; scrapeo del endpoint `/metrics` del runner + `postgres`.
- Acceso a Grafana por SSH tunnel (bind 127.0.0.1); no abrir ufw salvo decisión explícita.
- **Evidencia:** `deploy-observability-r1.log`, scrape OK, pantalla/URL de Grafana.

### R1.6 — Seguridad (S1)
- **Acción del usuario:** rotar el password sudo de `lenovosrv`.
- Saneado de evidencias históricas que contienen la credencial (p. ej. `docs/phases/16/evidence/deploy-applied-lenosrv.log`), sin reproducir el secreto.
- Verificar con `git diff` que no queda la credencial en archivos versionados ni en los nuevos docs.
- **Evidencia:** `sanitize-s1.log`.

### R1.7 — Seguimiento y cierre de los 7 días
- Check diario (uptime, eventos/día, sin crash, reportes generados) registrado como evidencia en `docs/phases/16/evidence/`.
- Al día 7: reporte de cierre del brazo no-LLM (trades, regímenes, informes, equity, estabilidad) → **gate de entrada a la Remediación 2**.

---

## Gobernanza transversal
- Ningún commit/push/merge/tag/deploy sin autorización explícita (Commit Candidate Report).
- Sin nuevas dependencias (R1.5 usa stdlib). Si aparece alguna, Dependency Proposal + USER GATE.
- `TRADING_MODE=paper`, `LIVE_TRADING_ENABLED=false` siempre.
- Evidencia con `harness/scripts/evidence.sh`; tests (unit/integration) verdes antes de declarar PASS.

# Reporte de Fase 04 — Real-Time Market Data

**Fecha:** 2026-08-23
**Estado de fase:** done
**Avance fase:** 100.0% · **Avance global:** 26.32%
**Gate:** approved

---

## 1. Executive Summary

Se implementó el Market Worker de tiempo real: cliente WebSocket de Bybit producción (spot) que mantiene un order book local sincronizado (profundidad 50, snapshot+deltas con reconciliación de secuencia `u`) y emite candles confirmadas al cierre. Incluye reconexión con backoff exponencial, detección STALE (gap de secuencia o timeout) y agregación de features de order book persistidas en `orderbook_feature_windows` (migración 0003). BTCUSDT se consume como contexto de solo lectura. 91 tests (93.07% cobertura branch), lint/typing/format verdes, smoke test real contra `wss://stream.bybit.com` (order book healthy + features persistidas). DP-005 APPROVED. Falta UAT + aprobación humana.

## 2. Objetivo

Stream de market data en tiempo real de Bybit producción: WebSocket, candles confirmadas, order book local con snapshot/deltas, reconexión, detección STALE y agregación a features persistentes (PRD §13–14, §63, Fase 04).

## 3. Scope

- `OrderBook` (dominio): bids/asks, snapshot, deltas con detección de gap (`u` no contiguo), quotes/depth/imbalance.
- `MarketDataHealth` (HEALTHY/STALE) + eventos de stream (`OrderBookSnapshot/Delta`, `KlineUpdate`).
- `BybitWebSocketClient` (`websockets` async): subscribe orderbook/kline, ping/pong, parseo con Pydantic.
- `MarketDataService`: orquestación — order book por símbolo, reconciliación, STALE (gap+timeout), candles confirmadas→`market_candles`, agregación→`orderbook_feature_windows`.
- Reconexión con backoff exponencial (techo 30s) en el CLI `market-worker`.
- Migración 0003 + repositorio de features; config (`bybit_ws_url`, depth, timeouts).
- Fixtures reales de WS grabados y versionados para tests offline.

## 4. Out of Scope

Indicadores técnicos (RSI/MACD/ATR…) y clasificación de régimen (Fase 05). Order book deltas brutos no se persisten (solo features, PRD §14). Auth privada/órdenes Testnet (Fase 12). Observabilidad OTel/Prometheus y métricas técnicas expuestas (Fase 13). Endpoints HTTP `/api/v1/market/*` (PRD §54): llegan con Fase 05/13.

## 5. Arquitectura antes/después

**Antes:** solo datos históricos (Fase 03): `BybitRestClient`, ingesta batch, `market_candles`/`dataset_manifests`. Sin tiempo real.
**Después:** plano de tiempo real — `src/domain/market/{orderbook,stream,features}.py`, `src/application/ports/{market_stream,orderbook_features}.py`, `src/application/services/market_data_service.py`, `src/infrastructure/bybit/{ws,ws_schemas}.py`, `src/interfaces/cli/market_worker.py`, tabla `orderbook_feature_windows` (migración 0003). Regla hexagonal respetada: el servicio orquesta contra Protocols; el cliente WS es reemplazable (connect inyectable).

## 6. Archivos creados

`src/domain/market/{orderbook,stream,features}.py`, `src/application/ports/{market_stream,orderbook_features}.py`, `src/application/services/market_data_service.py`, `src/infrastructure/bybit/{ws,ws_schemas}.py`, `src/interfaces/cli/market_worker.py`, `migrations/versions/0003_orderbook_features.py`, `tests/{test_orderbook,test_stream_events,test_bybit_ws,test_market_data_service,test_cli_market_worker}.py`, `tests/integration/test_orderbook_features.py`, `tests/fixtures/bybit_ws_{subscribe,snapshot,delta,kline_unconfirmed}.json`, `docs/phases/04/*`, `docs/superpowers/plans/2026-08-23-phase-04-real-time-market-data.md`.

## 7. Archivos modificados

`pyproject.toml`+`uv.lock` (websockets a runtime), `src/main.py` (subcomando `market-worker`), `src/settings.py`+`config/base.yaml` (bybit_ws_url, depth, stale_timeout, feature_window), `src/infrastructure/database/{models,repositories}.py` (OrderBookFeatureWindow + repo), `tests/{test_main,test_settings}.py`, `harness/state/progress.yaml`.

## 8. Dependencias

DP-005 **APPROVED**: `websockets 17.0.1` movido de transitiva (`uvicorn[standard]`) a runtime directa. Sin dependencias nuevas (Pydantic ya presente; asyncio/hashlib stdlib).

## 9. Configuración

`config/base.yaml` + `Settings`: `bybit_ws_url=wss://stream.bybit.com/v5/public/spot`, `bybit_orderbook_depth=50`, `stale_timeout_seconds=10.0`, `feature_window_seconds=5`. WS público (sin API key).

## 10. Comandos exactos (verificados)

```bash
uv add websockets                                       # DP-005: transitiva → runtime
POSTGRES_PASSWORD=trading uv run alembic upgrade head   # aplica 0003
POSTGRES_PASSWORD=trading uv run python -m main market-worker --symbols ETHUSDT BTCUSDT --timeframes 15m 1h --seconds 15
uv run pytest --cov=src --cov-branch --cov-fail-under=90  # 91 passed · 93.07%
uv run ruff check . && uv run ruff format --check .       # exit 0
uv run mypy src tests                                     # exit 0 (strict)
```

## 11. Rutas

`src/domain/market/`, `src/application/{ports,services}/`, `src/infrastructure/bybit/`, `src/infrastructure/database/`, `src/interfaces/cli/`, `migrations/`, `tests/fixtures/`, `docs/phases/04/evidence/`.

## 12. API endpoints

No se añadieron endpoints HTTP (el Market Worker es un proceso CLI, PRD §63). Endpoints de market data en Fase 05/13.

## 13. Migraciones

`0003_orderbook_features`: tabla `orderbook_feature_windows` (symbol, window_start/end_ms, best_bid/ask, spread, spread_pct, bid_depth, ask_depth, imbalance, created_at) + índice `(symbol, window_start_ms)`. Roundtrip up→down→up cubierto por `test_alembic.py`.

## 14. Tests

| Nivel | Ejecutado | Resultado | Evidencia |
|---|---|---|---|
| Unit | ☑ 88 casos (order book, stream, WS client con fixtures, service con fakes+clock, CLI reconnect/backoff) | PASS | evidence/unit-tests.log |
| Integration | ☑ 3 casos (alembic roundtrip + feature repo + market repo) | PASS (DB real) | evidence/unit-tests.log |
| E2E | ☑ market-worker real 15s contra Bybit WS + features persistidas | PASS | evidence/ws-smoke.log |

## 15. Coverage

**93.07%** (branch) — gate ≥90%. `docs/phases/04/evidence/coverage.json`.

## 16. E2E

`market-worker --symbols ETHUSDT BTCUSDT --timeframes 15m 1h --seconds 15` → conexión a `wss://stream.bybit.com/v5/public/spot` → snapshot+deltas aplicados → order book `healthy` → features persistidas cada 5s en `orderbook_feature_windows` (7 ventanas/símbolo acumuladas). `health final: healthy`, exit 0.

## 17. UAT

- Checklist: `docs/uat/phase-04-uat.md`
- Veredicto: APPROVED

## 18. Evidencias

Índice: `docs/phases/04/evidence/log.md` — lint, typing, format, unit-tests (+coverage.json), ws-smoke.

## 19. Métricas

8/8 entregables · 91 tests · cobertura 93.07% · order book profundidad 50 · features cada 5s · 1 migración.

## 20. Logs relevantes

Bugs reales detectados y corregidos durante el smoke test: (1) `run_with_reconnect` no imponía el deadline sobre `run_once` (bucle infinito) → `asyncio.wait_for(timeout=remaining)`; (2) el worker no hacía `commit` (los `flush` se revertían al cerrar sesión) → hook `commit=session.commit`; (3) health se reportaba `n/a` al cancelar por timeout → `health_holder` para reportar el health real.

## 21. Git diff

Nuevo plano de tiempo real + migración 0003 + CLI worker. Diff completo a solicitud; se generará en el Commit Candidate Report.

## 22. Riesgos

- Reconciliación por `u` (update id) por canal: si Bybit cambia la semántica de `u`, la detección de gap podría ser más estricta de lo necesario (resubscribe seguro).
- `feature_window_seconds` y `stale_timeout_seconds` son defaults globales; por entorno se ajustan en `config/<modo>.yaml` (fases posteriores).
- El worker es un proceso CLI; aún no hay supervisión de proceso (llegará con observabilidad, Fase 13).

## 23. Seguridad

WS público (sin API key). `websockets` (BSD-3) ya auditado (DP-005, reclasificación de transitiva). Sin secretos en repo. Deltas brutos no se persisten (solo features agregadas).

## 24. Deuda técnica

1. `ConnectFn = Callable[[str], Any]` en el cliente WS (perder tipado estricto del context manager a cambio de inyectabilidad simple).
2. La agregación usa `float` para precios/profundidad (consistente con Fase 03; precisión de portfolio es Fase 06).
3. `_consume_loop` mezcla el timeout de STALE con el `wait_for` de `recv`; si el intervalo de features > timeout de stale, la agregación no dispara puntualmente (aceptable con defaults 5s/10s).

## 25. Known Issues

- Warning `StarletteDeprecationWarning` (httpx/TestClient) heredado, no relacionado.
- `market-worker` no reanuda el order book tras reconexión si el snapshot inicial falla silenciosamente (se cubre por el bucle de reconexión; mejora posible en Fase 05).

## 26. Rollback

`uv remove websockets` (+ revertir pyproject/uv.lock); `alembic downgrade 0002`; borrar `src/domain/market/{orderbook,stream,features}.py`, `src/application/ports/{market_stream,orderbook_features}.py`, `src/application/services/market_data_service.py`, `src/infrastructure/bybit/{ws,ws_schemas}.py`, `src/interfaces/cli/market_worker.py`, `migrations/versions/0003_*`, tests asociados; revertir `src/main.py`, `settings.py`, `config/base.yaml`, `database/models.py`, `database/repositories.py`.

## 27. Competencias de Ingeniería de Software practicadas (PRD §80)

AsyncIO (asyncio, wait_for, task cancellation) · Networking (WebSocket, ping/pong) · WebSockets (snapshot+deltas, resubscribe) · Fault Tolerance (reconexión, backoff, STALE) · State Management (order book local, reconciliación de secuencia) · Architecture (hexagonal, Protocols, inyección de dependencias) · Testing (TDD, fixtures reales, fakes con clock) · Databases (migración Alembic).

## 28. Definition of Done

scope complete ☑ · tests PASS ☑ · integration PASS ☑ · E2E ☑ · UAT approved ☑ · coverage ≥90% ☑ (93.07%) · CI green ☐ N/A · lint ☑ typing ☑ format ☑ · documentation ☑ · evidence ☑ · diff reviewed ☐ · user approved ☑

## 29. Estado CI

`ci.yml` existente: `quality` (ruff/mypy), `integration` (pytest contra postgres). Los tests de WS usan fixtures grabados (sin red en CI). El smoke test real es manual (UAT), nunca en CI (bybit-integration). No ejecutable en GitHub hasta push autorizado.

## 30. Solicitud de aprobación

- [x] Presentado al usuario (junto con instructivo UAT `docs/uat/phase-04-uat.md`)
- **DECISIÓN DEL USUARIO:** ☑ APPROVED ☐ REJECTED
- Comentario: aprobado vía selector OpenCode (UAT APPROVED, gate approved)

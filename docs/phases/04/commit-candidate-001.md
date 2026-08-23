# Commit Candidate Report — 2026-08-23 (Fase 04)

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

Fase 04 (Real-Time Market Data): cliente WebSocket de Bybit producción, order book local (profundidad 50, snapshot+deltas con reconciliación), candles confirmadas, reconexión con backoff, detección STALE y agregación de features persistidas. DP-005 (websockets→runtime) aplicado.

## Rama

| Campo | Valor |
|---|---|
| branch | main |
| base commit | d28976a fix(tests): test_load_settings hermético ante env de CI |

## Archivos

- **Creados (30):** dominio `src/domain/market/{orderbook,stream,features}.py`; puertos `src/application/ports/{market_stream,orderbook_features}.py`; servicio `src/application/services/market_data_service.py`; infra `src/infrastructure/bybit/{ws,ws_schemas}.py`; CLI `src/interfaces/cli/market_worker.py`; migración `migrations/versions/0003_*`; 6 archivos de test + 4 fixtures WS + 1 test integración; `docs/phases/04/*`, `docs/phases/phase-04-report.md`, `docs/uat/phase-04-uat.md`, plan.
- **Modificados (9):** `pyproject.toml`+`uv.lock`, `src/main.py`, `src/settings.py`, `config/base.yaml`, `src/infrastructure/database/{models,repositories}.py`, `tests/test_main.py`, `harness/state/progress.yaml`.
- **Eliminados:** ninguno.

## Diff

```bash
git diff --cached --stat  # 40 archivos (~2900 líneas nuevas)
```

## Arquitectura afectada

Nuevo plano de tiempo real: dominio (`OrderBook`, `MarketDataHealth`, eventos) → puertos (`MarketDataStream`, `OrderBookFeatureRepository`) → adaptadores (`BybitWebSocketClient`, repo de features) → orquestación (`MarketDataService`) → CLI `market-worker`. Migración `0003` (`orderbook_feature_windows`). Sin cambios en dominio existente ni API HTTP.

## Índice del grafo

- [ ] Índice re-indexado tras el commit (`index_repository`) — pendiente (grafo actual es pre-Fase-04).
- [ ] Cobertura verificada sobre archivos tocados (`check_index_coverage`) — tras re-indexar.

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Unit + Integration | 91 passed | docs/phases/04/evidence/unit-tests.log |
| WS smoke real | exit 0, health healthy | docs/phases/04/evidence/ws-smoke.log |

## Cobertura

**93.07%** (branch) — gate ≥90%. `docs/phases/04/evidence/coverage.json`.

## Calidad

```bash
uv run ruff check .        # All checks passed
uv run ruff format --check .   # already formatted
uv run mypy src tests      # Success: no issues found (strict)
uv run pytest              # 91 passed
```

## Seguridad

- [x] Sin secretos en el diff (WS público, sin API key)
- [x] Sin .env ni credenciales
- [x] Deltas brutos no se persisten (solo features)

## Riesgos

- Reconciliación por `u` (update id); resubscribe seguro ante gap.
- Worker es proceso CLI sin supervisión (Fase 13).

## Deuda técnica

1. `ConnectFn = Callable[[str], Any]` (tipado relajado para inyectabilidad).
2. Agregación con `float` (precisión de portfolio en Fase 06).
3. `_consume_loop` mezcla timeout STALE con wait_for de recv (aceptable con defaults).

## Mensaje de commit propuesto

```
feat(phase-04): Real-Time Market Data

- cliente WebSocket Bybit (spot) con snapshot+deltas y reconciliación de secuencia
- order book local (profundidad 50) + MarketDataHealth HEALTHY/STALE
- candles confirmadas al cierre → market_candles
- reconexión con backoff exponencial + detección STALE (gap+timeout)
- agregación de features de order book → orderbook_feature_windows (migración 0003)
- CLI market-worker · websockets a runtime (DP-005) · 91 tests · cobertura 93.07%
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

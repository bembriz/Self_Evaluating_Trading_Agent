# UAT — Fase 04: Real-Time Market Data

> Prueba de aceptación de usuario (HITL). El agente NO puede aprobar UAT.
> Ejecuta los pasos tal cual y completa "Resultado observado" y el veredicto final.

## Precondiciones

| # | Precondición | Verificada ☐ |
|---|---|---|
| 1 | `uv` instalado y `uv sync` ya ejecutado | ☐ |
| 2 | Postgres activo en 127.0.0.1:5433 y `.env`/env con `POSTGRES_PASSWORD` | ☐ |
| 3 | Acceso a internet (wss://stream.bybit.com es público) | ☐ |
| 4 | Terminal en la raíz del repositorio | ☐ |

## Entradas / Datos

`POSTGRES_PASSWORD` (env). Sin API key (WebSocket público spot).

## Pasos

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | `POSTGRES_PASSWORD=trading uv run alembic upgrade head` | Migración `0003` aplicada, exit 0 |
| 2 | `POSTGRES_PASSWORD=trading uv run python -m main market-worker --symbols ETHUSDT BTCUSDT --timeframes 15m 1h --seconds 15` | `[market-worker] health final: healthy`, exit 0 |
| 3 | `PGPASSWORD=trading psql -h localhost -p 5433 -U trading -d trading_agent -c "SELECT symbol, count(*) FROM orderbook_feature_windows GROUP BY symbol"` | Filas por `ETHUSDT` y `BTCUSDT` con `count > 0` |
| 4 | `uv run pytest --cov=src --cov-branch --cov-fail-under=90` | `91 passed` y cobertura ≥90% |
| 5 | `uv run ruff check . && uv run ruff format --check . && uv run mypy src tests` | Todo verde |
| 6 | `uv run python -m main market-worker --timeframes 5m` | Error `ValueError: timeframe desconocido: 5m` (valida timeframes) |

## Evidencia a adjuntar

Salida de cada comando (pasos 1–6).

## Resultado observado

| Paso | Resultado observado | ¿Coincide? (SÍ/NO) | Notas |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |
| 6 | | | |

## Incidencias encontradas

> Desviaciones, errores o comportamientos inesperados.

---

## VEREDICTO UAT: APPROVED
<!-- Sustituir PENDING por APPROVED o REJECTED. gate_check exige el veredicto APPROVED visible (los comentarios HTML no cuentan) al check uat-approved -->
Decisor: usuario  Fecha: 2026-08-23
Comentario: aprobado vía selector OpenCode

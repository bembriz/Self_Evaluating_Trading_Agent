# UAT — Fase 03: Historical Market Data

> Prueba de aceptación de usuario (HITL). El agente NO puede aprobar UAT.
> Ejecuta los pasos tal cual y completa "Resultado observado" y el veredicto final.

## Precondiciones

| # | Precondición | Verificada ☐ |
|---|---|---|
| 1 | `uv` instalado y `uv sync` ya ejecutado | ☐ |
| 2 | Postgres activo en 127.0.0.1:5433 y `.env`/env con `POSTGRES_PASSWORD` | ☐ |
| 3 | Acceso a internet (api.bybit.com es un endpoint público) | ☐ |
| 4 | Terminal en la raíz del repositorio | ☐ |

## Entradas / Datos

`POSTGRES_PASSWORD` (env). Para no tocar el dataset oficial, el paso 2 usa `--dataset-version UAT_V001` y un rango corto (`--months 1`). El dataset oficial `BYBIT_ETHBTC_V001` ya fue descargado por el agente; el paso 3 solo lo verifica.

## Pasos

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | `POSTGRES_PASSWORD=trading uv run alembic upgrade head` | Migración `0002` aplicada, exit 0 |
| 2 | `POSTGRES_PASSWORD=trading uv run python -m main download --dataset-version UAT_V001 --symbols ETHUSDT --timeframes 15m 1h --months 1` | JSON con `rows` y `sha256` por archivo, exit 0, sin warnings |
| 3 | `uv run python -m main verify --dataset-version BYBIT_ETHBTC_V001` | 6 líneas `OK` con `rows=` correctos y `exit=0` |
| 4 | `uv run pytest --cov=src --cov-branch --cov-fail-under=90` | `56 passed` y cobertura ≥90% |
| 5 | `uv run ruff check . && uv run ruff format --check . && uv run mypy src tests` | Todo verde ("All checks passed", "already formatted", "Success") |
| 6 | `cat docs/datasets/BYBIT_ETHBTC_V001.manifest.json` | Manifest con `dataset_version`, `source`, `symbols`, `timeframes`, 6 `files` con `row_count` y `sha256`, `schema_version` y `download_command` |
| 7 | `PGPASSWORD=trading psql -h localhost -p 5433 -U trading -d trading_agent -c "SELECT timeframe, count(*) FROM market_candles GROUP BY timeframe ORDER BY timeframe"` | 15m/1h/4h con ~207360 / ~51840 / ~12960 filas (2 symbols cada uno) |

## Evidencia a adjuntar

Salida de cada comando (pasos 1–7).

## Resultado observado

| Paso | Resultado observado | ¿Coincide? (SÍ/NO) | Notas |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |
| 6 | | | |
| 7 | | | |

## Incidencias encontradas

> Desviaciones, errores o comportamientos inesperados.

---

## VEREDICTO UAT: APPROVED
<!-- Sustituir PENDING por APPROVED o REJECTED. gate_check exige el veredicto APPROVED visible (los comentarios HTML no cuentan) al check uat-approved -->
Decisor: usuario  Fecha: 2026-08-23
Comentario: aprobado vía selector OpenCode

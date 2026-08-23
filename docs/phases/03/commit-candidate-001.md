# Commit Candidate Report — 2026-08-23

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

Fase 03 (Historical Market Data): adapter REST histórico de Bybit, dominio de market data, validación, ingesta con persistencia CSV + PostgreSQL, manifest con SHA-256, CLI `download`/`verify`, y dataset congelado `BYBIT_ETHBTC_V001` (36 meses, 272.160 velas). DP-004 (httpx→runtime) aplicado.

## Rama

| Campo | Valor |
|---|---|
| branch | main |
| base commit | 36c4601 feat(phase-02): PostgreSQL & Application Skeleton |

## Archivos

- **Creados:** `src/domain/market/{candle,dataset}.py`, `src/application/ports/{market_data,dataset_store,market_repositories}.py`, `src/application/services/{validation,historical_data}.py`, `src/infrastructure/bybit/{client,schemas}.py`, `src/infrastructure/storage/dataset_store.py`, `src/interfaces/cli/download.py`, `migrations/versions/0002_market_data.py`, 8 archivos de test, `tests/fixtures/bybit_kline_spot.json`, `docs/datasets/BYBIT_ETHBTC_V001.manifest.json`, `docs/phases/03/*` (DP-004 + evidencias), `docs/phases/phase-03-report.md`, `docs/uat/phase-03-uat.md`, plan en `docs/superpowers/plans/`.
- **Modificados:** `src/infrastructure/database/{models,repositories}.py`, `src/main.py`, `src/settings.py`, `config/base.yaml`, `pyproject.toml`+`uv.lock`, `tests/{test_models,test_main}.py`, `.gitignore` (ancla `/datasets/`, `/coverage.json`), `harness/state/progress.yaml`.
- **Eliminados:** ninguno.

## Diff

```bash
git diff --stat  # 10 modificados + ~35 creados; ~2900 líneas nuevas (src+tests)
# diff completo: git diff --cached
```

## Arquitectura afectada

Nuevo plano de market data (hexagonal): dominio puro (`Candle`, `Timeframe`, `DatasetManifest`) → puertos (`MarketDataClient`, `DatasetStore`, `MarketCandleRepository`, `DatasetManifestRepository`) → adaptadores (`BybitRestClient`, `LocalDatasetStore`, repos SQLAlchemy) → orquestación (`HistoricalDataService`) → CLI. Migración `0002` añade `market_candles` y `dataset_manifests`. `main.py` gana subcomandos. Sin cambios en el dominio existente ni en la API HTTP.

## Índice del grafo

- [ ] Índice re-indexado tras el commit (`index_repository`) — pendiente (el grafo actual es pre-Fase-03; `detect_changes` devuelve `seed_symbols: 0` por archivos no indexados aún).
- [ ] Cobertura verificada sobre archivos tocados (`check_index_coverage`) — tras re-indexar.

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Unit + Integration + E2E | 56 passed | docs/phases/03/evidence/unit-tests.log |
| Download real 36m | exit 0 (6 archivos) | docs/phases/03/evidence/download.log |
| Verify SHA-256 + reload | exit 0 (6/6 OK) | docs/phases/03/evidence/verify.log |

## Cobertura

**92.49%** (branch) — gate ≥90%. `docs/phases/03/evidence/coverage.json`.

## Calidad

```bash
uv run ruff check .        # All checks passed (exit 0)
uv run ruff format --check .   # already formatted (exit 0)
uv run mypy src tests      # Success: no issues found (strict)
uv run pytest              # 56 passed
```

## Seguridad

- [x] Sin secretos en el diff (endpoint kline público, sin API key)
- [x] Sin archivos .env ni credenciales
- [x] `datasets/` (datos crudos) sigue gitignored; manifest solo con metadatos + SHA-256

## Riesgos

- `docs/datasets/` quedaba ignorado por la regla `datasets/` sin ancla → corregido a `/datasets/`.
- Upsert de 103.680 filas excedía el límite de parámetros de Postgres → corregido con lotes de 1000.

## Deuda técnica

1. `.env.example` sigue sin `POSTGRES_PASSWORD=` (heredado de Fase 02).
2. `_months_ago_ms` usa 30 días/mes (el rango exacto lo fija el manifest).
3. `download` no reanuda a mitad de archivo (re-ejecución idempotente por upsert).

## Mensaje de commit propuesto

```
feat(phase-03): Historical Market Data

- adapter REST histórico Bybit (spot, kline v5) con paginación + retries
- dominio Candle/Timeframe/DatasetManifest + validación de calidad
- ingesta: CSV congelado + PostgreSQL (market_candles, dataset_manifests)
- manifest con SHA-256 + CLI download/verify
- dataset BYBIT_ETHBTC_V001 (36 meses, 272.160 velas) + migración 0002
- httpx a runtime (DP-004) · 56 tests · cobertura 92.49%
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

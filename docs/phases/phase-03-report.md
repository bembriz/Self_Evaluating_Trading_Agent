# Reporte de Fase 03 — Historical Market Data

**Fecha:** 2026-08-23
**Estado de fase:** done
**Avance fase:** 100.0% · **Avance global:** 20.53%
**Gate:** approved

---

## 1. Executive Summary

Se implementó la ingesta de datos históricos de Bybit (REST v5, spot) para ETHUSDT/BTCUSDT en 15m/1h/4h. El dataset oficial `BYBIT_ETHBTC_V001` quedó congelado con 36 meses de velas (272.160 filas, 6 archivos CSV), manifest versionado en git con SHA-256 por archivo, y persistencia paralela en PostgreSQL (`market_candles` + `dataset_manifests`, migración 0002). El flujo completo download→validate→persist→checksum→reload está cubierto por 56 tests (92.49% cobertura branch), lint/typing/format verdes. DP-004 APPROVED. Falta UAT + aprobación humana.

## 2. Objetivo

Descargar ≥36 meses de histórico Bybit (ETHUSDT/BTCUSDT, 15m/1h/4h), validar calidad/completitud, persistir en CSV congelado + PostgreSQL, y generar manifest con SHA-256 reproducible (PRD §40–41, §55, Fase 03).

## 3. Scope

- Adapter REST histórico de Bybit (`GET /v5/market/kline`, spot) con paginación, retries/backoff y validación de esquema.
- Dominio puro: `Candle`, `Timeframe`, `DatasetManifest`/`CandleFileEntry`.
- Puertos: `MarketDataClient`, `DatasetStore`, `MarketCandleRepository`, `DatasetManifestRepository`.
- Validación de calidad (orden, unicidad, alineación, huecos) — nunca descarta filas.
- DatasetStore (CSV + SHA-256 + manifest JSON) con roundtrip exacto.
- Persistencia PostgreSQL: `market_candles` (upsert idempotente en lotes) + `dataset_manifests`.
- Servicio de orquestación `HistoricalDataService` + CLI `download`/`verify`.
- Dataset congelado `BYBIT_ETHBTC_V001` (36 meses, 272.160 velas) con manifest en git y checksums verificados.

## 4. Out of Scope

WebSocket/tiempo real, order book y detección STALE (Fase 04). Features/indicadores (Fase 05). Separación temporal train/holdout congelada (Fase 06+). `pgvector` (paquete Python) sigue en Fase 09. Endpoints HTTP de market data (PRD §54) no añadidos aquí (el CLI cubre la ingesta).

## 5. Arquitectura antes/después

**Antes:** persistencia solo `system_state` + FastAPI base; `src/infrastructure/bybit/` y `src/domain/market/` vacíos.
**Después:** plano de market data — `src/domain/market/{candle,dataset}.py`, `src/application/ports/{market_data,dataset_store,market_repositories}.py`, `src/application/services/{validation,historical_data}.py`, `src/infrastructure/bybit/{client,schemas}.py`, `src/infrastructure/storage/dataset_store.py`, repos SQLAlchemy de market data, `src/interfaces/cli/download.py`. Regla hexagonal respetada: el servicio orquesta contra Protocols, no contra adaptadores.

## 6. Archivos creados

`src/domain/market/{candle,dataset}.py`, `src/application/ports/{market_data,dataset_store,market_repositories}.py`, `src/application/services/{validation,historical_data}.py`, `src/infrastructure/bybit/{client,schemas}.py`, `src/infrastructure/storage/dataset_store.py`, `src/interfaces/cli/download.py`, `migrations/versions/0002_market_data.py`, `tests/{test_candle,test_dataset,test_validation,test_bybit_client,test_dataset_store,test_historical_service,test_cli_download}.py`, `tests/integration/test_market_repository.py`, `tests/fixtures/bybit_kline_spot.json`, `docs/phases/03/*`, `docs/datasets/BYBIT_ETHBTC_V001.manifest.json`, `docs/superpowers/plans/2026-08-23-phase-03-historical-market-data.md`.

## 7. Archivos modificados

`pyproject.toml` (httpx a runtime), `uv.lock`, `src/main.py` (subcomandos), `src/settings.py` (bybit_* + dataset_dir), `config/base.yaml` (bybit_* + dataset_dir), `src/infrastructure/database/{models,repositories}.py` (MarketCandle + DatasetManifestRecord + repos), `tests/{test_models,test_main}.py`, `harness/state/progress.yaml` (vía scripts).

## 8. Dependencias

DP-004 **APPROVED**: `httpx 0.28.1` movido de dev a runtime (adapter Bybit). Sin dependencias nuevas (se reutilizó httpx ya presente; CSV/hashlib stdlib).

## 9. Configuración

`config/base.yaml` + `Settings`: `bybit_base_url=https://api.bybit.com`, `bybit_request_timeout=10.0`, `dataset_dir=datasets`. El endpoint kline spot es público (sin API key). Postgres se conecta con `POSTGRES_PASSWORD` vía `.env`/env (patrón existente).

## 10. Comandos exactos (verificados)

```bash
uv add httpx                                             # DP-004: dev → runtime
POSTGRES_PASSWORD=trading uv run alembic upgrade head    # aplica 0002
POSTGRES_PASSWORD=trading uv run python -m main download --dataset-version BYBIT_ETHBTC_V001
uv run python -m main verify --dataset-version BYBIT_ETHBTC_V001
uv run pytest --cov=src --cov-branch --cov-fail-under=90 # 56 passed · 92.49%
uv run ruff check . && uv run ruff format --check .      # exit 0
uv run mypy src tests                                    # exit 0 (strict)
```

## 11. Rutas

`src/domain/market/`, `src/application/{ports,services}/`, `src/infrastructure/{bybit,storage}/`, `src/infrastructure/database/`, `src/interfaces/cli/`, `migrations/`, `datasets/BYBIT_ETHBTC_V001/` (gitignored), `docs/datasets/` (manifest versionado), `docs/phases/03/evidence/`.

## 12. API endpoints

No se añadieron endpoints HTTP en esta fase (ingesta vía CLI `download`/`verify`).

## 13. Migraciones

`0002_market_data`: tablas `market_candles` (unique `symbol,timeframe,timestamp_ms` + índice) y `dataset_manifests` (PK `dataset_version`). Roundtrip up→down→up cubierto por `test_alembic.py` contra Postgres real.

## 14. Tests

| Nivel | Ejecutado | Resultado | Evidencia |
|---|---|---|---|
| Unit | ☑ 51 casos (dominio, validación, bybit client con MockTransport, dataset store, servicio con fakes, CLI) | PASS | evidence/unit-tests.log |
| Integration | ☑ 5 casos (alembic roundtrip + repos market data, upsert lotes) | PASS (DB real) | evidence/unit-tests.log |
| E2E | ☑ download real 36m + verify SHA-256 + reload | PASS | evidence/download.log, verify.log |

## 15. Coverage

**92.49%** (branch) — gate ≥90%. `docs/phases/03/evidence/coverage.json`.

## 16. E2E

`download BYBIT_ETHBTC_V001` (36 meses × 2 symbols × 3 timeframes) → 272.160 velas, 0 warnings de validación → CSV persistidos + upsert en `market_candles` (en lotes de 1000) → manifest JSON con SHA-256 → `verify` recomputa checksums y re-cuenta filas: 6/6 OK.

## 17. UAT

- Checklist: `docs/uat/phase-03-uat.md`
- Veredicto: APPROVED

## 18. Evidencias

Índice: `docs/phases/03/evidence/log.md` — lint, typing, format, unit-tests (+coverage.json), download, verify.

## 19. Métricas

7/7 entregables · 56 tests · cobertura 92.49% · 272.160 velas (ETH 15m 103.680, ETH 1h 25.920, ETH 4h 6.480, BTC idem) · rango 2023-09-08 → 2026-08-23 · 1 migración.

## 20. Logs relevantes

Descarga completa sin warnings de validación (datos continuos y alineados). Bugs reales detectados y corregidos durante el smoke test: (1) Bybit devuelve velas en orden descendente → `earliest` se computa con `min()`, no `batch[0]`; (2) upsert de 103.680 filas superaba el límite de parámetros de PostgreSQL → upsert en lotes de 1000; (3) `path` del manifest perdía el prefijo `datasets/`; (4) `main()` sin args caía en `sys.argv` de pytest → argv explícito desde `__main__`.

## 21. Git diff

Nuevo plano de market data + persistencia + CLI + migración 0002. Diff completo a solicitud; se generará en el Commit Candidate Report.

## 22. Riesgos

- El dataset congelado es 36 meses a fecha de hoy (2026-08-23); un re-fetch futuro variará el rango final (por diseño, inmutable una vez congelado por versión).
- Endpoint kline público sin rate limit persistente documentado: el client implementa retries con `Retry-After` y backoff+jitter.
- `float64` para precios/volúmenes (suficiente para market data; la contabilidad exacta de portfolio es de Fase 06).

## 23. Seguridad

Sin secretos en repo (endpoint kline público). `datasets/` sigue gitignored (PRD §40). Manifest en git solo con metadatos + SHA-256, sin datos crudos. `httpx` (BSD-3) ya auditado en DP-003; reclasificado a runtime en DP-004.

## 24. Deuda técnica

1. `.env.example` no incluye `POSTGRES_PASSWORD=` (heredado de Fase 02, deuda registrada allí); el CLI requiere `POSTGRES_PASSWORD` por env.
2. `_months_ago_ms` usa 30 días/mes (aproximación); el rango exacto queda fijado por el manifest, no por el cálculo.
3. `bybit_request_timeout` global (sin timeout por request diferenciado).

## 25. Known Issues

- Warning `StarletteDeprecationWarning` sobre `httpx`/TestClient (heredado, no relacionado con esta fase).
- `download` no es reanudable a mitad de archivo (si falla a los N de 6 archivos, re-ejecutar es idempotente por el upsert, pero re-escribe los CSV ya completados).

## 26. Rollback

`uv remove httpx` + revertir a dev (`uv add --dev httpx`); `alembic downgrade 0001`; borrar `src/domain/market/`, `src/infrastructure/bybit/`, `src/infrastructure/storage/`, `src/interfaces/cli/download.py`, `src/application/ports/{market_data,dataset_store,market_repositories}.py`, `src/application/services/{validation,historical_data}.py`, `migrations/versions/0002_market_data.py`, tests asociados; revertir `src/main.py`, `src/settings.py`, `config/base.yaml`, `src/infrastructure/database/{models,repositories}.py`; `rm -rf datasets/ docs/datasets/`.

## 27. Competencias de Ingeniería de Software practicadas (PRD §80)

Data Engineering (pipeline download→validate→persist→checksum→reload, idempotencia, validación de calidad) · APIs (cliente REST v5 con paginación, retries, rate limit) · Validation (schema Pydantic, invariantes OHLC, alineación/huecos) · Reproducibility (manifest + SHA-256 + dataset versionado) · Testing (TDD, MockTransport, fakes, integración DB) · Architecture (hexagonal, Protocols, composition root) · Databases (migración Alembic, upsert ON CONFLICT).

## 28. Definition of Done

scope complete ☑ · tests PASS ☑ · integration PASS ☑ · E2E ☑ · UAT approved ☑ · coverage ≥90% ☑ (92.49%) · CI green ☐ N/A · lint ☑ typing ☑ format ☑ · documentation ☑ · evidence ☑ · diff reviewed ☐ · user approved ☑

## 29. Estado CI

`ci.yml` existente (Fase 01) sigue verde a nivel local; la fase no añade jobs nuevos (integración de market data corre dentro del job `integration` existente con servicio postgres). No ejecutable en GitHub hasta push autorizado.

## 30. Solicitud de aprobación

- [x] Presentado al usuario (junto con instructivo UAT `docs/uat/phase-03-uat.md`)
- **DECISIÓN DEL USUARIO:** ☑ APPROVED ☐ REJECTED
- Comentario: aprobado vía selector OpenCode (UAT APPROVED, gate approved)

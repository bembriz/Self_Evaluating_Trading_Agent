# Commit Candidate Report — 2026-09-28

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

Registrar M5 (Silver Candles Multi-Timeframe): agregación determinista de los 3 días
DEVELOPMENT de Silver trades hacia los 7 timeframes (`1m 5m 15m 30m 1h 4h 1d`) en
`/srv/data/medallion/silver/candles/ETHUSDT/` — OHLCV por ventana calendario UTC
`[open, close)`, Decimal exacto sin float, sin gap filling, linaje completo en manifest
por output, con 54 unit tests, UAT RUN1/RUN2/determinismo/negativos en el servidor y la
marca `23/m5-silver-candles` = done en el ledger.

## Rama

| Campo | Valor |
|---|---|
| branch | `medalion` |
| base commit | `d2aef304239df55d7b20dcd740ae898d6c5b90ac` (= `origin/medalion`) |

## Archivos

- **Creados (14):**
  - `src/infrastructure/medallion/candles.py` — `transform_day/transform_days`: split
    guard → hash Silver (manifest + row_count) → lectura/validación total (FAIL CLOSED
    sin crear árbol destino) → agregación OHLCV Decimal → gzip determinista `.part` →
    round-trip → manifest atómico → rename → ops log
  - `src/infrastructure/medallion/candles_cli.py` — CLI stdlib
    (`--trades-dir --dest-dir --symbol --dates --require-marker`), exit 0/1/2
  - `tests/test_silver_candles.py` — 45 funciones de test / 54 casos sin red
  - `docs/phases/23/m5-silver-candles.md` — doc de milestone
  - `docs/phases/23/evidence/m5-*` — 9 evidencias (unit/quality/preflight/deploy/RUN1/
    validación independiente/RUN2+determinismo/negativos/Bronze intacto)
  - `docs/phases/23/commit-candidate-007.md` — este reporte
- **Modificados (2):** `docs/phases/23/evidence/log.md`, `harness/state/progress.yaml`
  (`23/m5-silver-candles` → `done` vía `progress.py mark-done`)
- **Eliminados:** ninguno

## Diff

```bash
$ git diff --cached --shortstat
16 files changed, 2004 insertions(+), 2 deletions(-)
$ git diff --cached --check
rc=0   # 0 hallazgos
```

## Arquitectura afectada

- Amplía `infrastructure.medallion` con la capa Silver candles (ADR-0005/0007,
  `docs/design/medallion-replay-architecture.md` §6). `bronze.py`, `silver.py`,
  `split_guard.py` y la capa Bronze **no se modifican**; consumidor futuro = M6 (Gold).
- lenovosrv (fuera de git): creados 21 outputs + manifest + ops en
  `/srv/data/medallion/silver/candles/ETHUSDT/`; Silver trades y Bronze intactos
  (hashes verificados `m5-03`/`m5-09`); contenedores productivos intactos.
- Sin dependencias nuevas (stdlib: `csv`, `gzip`, `decimal`).

## Índice del grafo

- [ ] Índice re-indexado tras el commit (`index_repository`) — pendiente post-commit
- [ ] Cobertura verificada sobre archivos tocados (`check_index_coverage`) — pendiente
      post-commit (`docs/` y `harness/state` excluidos por diseño)

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| `pytest tests/test_silver_candles.py tests/test_silver_trades.py tests/test_bronze_ingest.py --cov=infrastructure.medallion` | PASS — cobertura **95.10%** (candles.py **100%**) | `m5-01-unit-tests.log` |
| `ruff check .` + `ruff format --check .` + `mypy src tests` + `pytest tests --ignore=tests/integration` | PASS — **1067 passed, 1 skipped** | `m5-02-repo-quality.log` |
| Preflight lenovosrv (fuente 1 880 793 + hashes) | PASS | `m5-03-preflight.log` |
| UAT RUN1 (7 tf × 3 días) | PASS — `transformed=21`, 21 outputs | `m5-05-uat-run1.log` |
| Validación independiente OHLC/volume/count/UTC (recomputo completo) | PASS — 0 mismatches, `SYNTHETIC_CANDLES=0`, suma trade_count = 1 880 793 por tf | `m5-06-ohlc-validation.log` |
| UAT RUN2 + determinismo (dir fresco) | PASS — `skipped=21`, `RUN2_CHANGED=0`, mismos hashes | `m5-07-uat-run2-determinism.log` |
| UAT negatives (WF/holdout/pre-DEV/fecha/marker/hash guard) | PASS — exit 1/1/1/2/1/1, guard ANTES de leer | `m5-08-uat-negative.log` |
| Bronze intacto post-UAT | PASS — 3 hashes OK | `m5-09-bronze-untouched.log` |

## Cobertura

- `candles.py` **100%** statements/branch; `candles_cli.py` 94%; capa medallion
  **95.10%** con `--cov=infrastructure.medallion --cov-branch --cov-fail-under=90` → PASS
- Suite completa producto: **1067 passed, 1 skipped** (PG local caído = preexistente)

## Calidad

```bash
uv run ruff check .                 # All checks passed!
uv run ruff format --check .        # all files formatted
uv run mypy src tests               # Success: no issues found in 279 source files
uv run pytest tests --ignore=tests/integration
                                    # 1067 passed, 1 skipped
```

## Seguridad

- [x] Sin secretos en el diff (grep `password|api_key|secret|token|BEGIN … PRIVATE` → 0 hits)
- [x] Sin archivos `.env` ni credenciales; evidencia m5 sin sudo ni credenciales
- [x] Preexistente y NO de este commit: credencial sudo histórica ya versionada en logs
  de fase 16 → "Credencial sudo histórica detectada en evidencia ya versionada. Rotación
  requerida y limpieza de historial pendiente en gate separado."
  (`SECURITY_CREDENTIAL_ROTATION_REQUIRED=YES`, `GIT_HISTORY_CLEANUP_REQUIRED=YES`)

## Riesgos

- Bajo: código nuevo aislado (`candles.py`/`candles_cli.py`), solo consumido por su CLI y
  sus tests; Silver trades y Bronze intocados (solo lectura + hash check).
- La validación independiente del servidor reimplementa la agregación sin importar el
  módulo (separación real de código), lo que reduce el riesgo de "mismo bug en ambos".
- Si M6+ necesita timeframes que NO dividen el día (p. ej. `8h` ok, pero ventanas no
  alineadas), el guard `close_time <= fin del día` fallará FAIL CLOSED por diseño.

## Deuda técnica

- `coverage.json` global de repo no re-ejecutado en M5 (umbral del gate de fase al cierre).
- M6 (Gold) consumirá trades + candles; referenciar hashes de ambos en el manifest.
- Reconciliación vs API Kline (validación, no fuente) queda para M9/re-ejecución.
- Rotación de credencial + limpieza de historial → gate separado (preexistente).

## Mensaje de commit propuesto

```
feat(medallion): M5 deterministic multi-timeframe Silver candles

- candles.py: trades Silver -> candles 1m/5m/15m/30m/1h/4h/1d (ventana UTC
  [open, close), sin gap filling, solo velas cerradas dentro del dia fuente);
  OHLC por orden canonico de Silver; volume Decimal exacto (nunca float);
  precios byte-a-byte; trade_count
- guards: split DEVELOPMENT antes de leer; hash Silver (manifest + row_count)
  FAIL CLOSED; fila invalida FAIL CLOSED sin crear arbol destino; .part +
  round-trip + manifest atomico + rename; rerun verifica hash + linaje -> skip
- manifest por output con linaje (source_trades path+sha, output sha,
  candle_count, min/max open_time, duration_ms, schema_version)
- candles_cli.py: CLI stdlib para lenovosrv (exit 0/1/2)
- tests: 54 casos; candles.py 100% branch; capa medallion 95.10%;
  suite 1067 passed
- UAT lenovosrv: RUN1 transformed=21 (4320/864/288/144/72/18/3 velas por tf),
  RUN2 skipped=21 (0 changed), determinismo dir fresco identico; recomputo
  independiente 0 mismatches; WF/holdout rechazados antes de leer
  (WF_READS=0, FINAL_HOLDOUT_READS=0); Bronze intacto
- ledger: 23/m5-silver-candles -> done (via progress.py mark-done)
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

# M9-A1 — Evolución de schema de la fuente Bybit Spot (V1/V2) + backfill de metadata

**Fecha:** 2026-09-28 (UTC-6)
**Rama:** `medalion` @ `dc5c0a2d791686e25a54661a81902a17564ef4b0` (0 commits más allá de la base;
verificado antes y después de la ejecución)
**Alcance:** adaptar el pipeline Medallion a la evolución real del esquema de la fuente
`https://public.bybit.com/spot/<SYMBOL>/<SYMBOL>_YYYY-MM-DD.csv.gz` — **V1** = 5 columnas
(`id,timestamp,price,volume,side`) vs **V2** = 6 columnas con `rpi` final — con TDD, corrección
determinista de la metadata Bronze, backfill del linaje Silver y UAT sobre **solo `2025-03-13`**
más 3 fechas V2 de humo. **NO bulk de los 96, NO candles/gold/replay, NO commit.**
**Gate:** instrucción directa del usuario (M9-A1).

## 1. Diagnóstico previo (M9-A recovery, ya ejecutado)

- `m9a-recovery-05-silver-resume.log` → `exit=1`:
  `ERROR: date=2025-03-13/ETHUSDT_2025-03-13.csv.gz: header ('id','timestamp','price','volume','side','rpi') != ('id','timestamp','price','volume','side')`
- `m9a-recovery-06-schema-diag.log` → histograma de la fuente real:
  **551 archivos V1** (`2023-09-09..2025-03-12`) · **96 archivos V2** (`2025-03-13..2025-06-16`).
- `rpi` ausente del código de producto (0 matches); los 96 días V2 están **dentro** de
  DEVELOPMENT (`WALK_FORWARD_READS_AFFECTED=0`, `FINAL_HOLDOUT_READS_AFFECTED=0`).
- Regla aplicada (skill `bybit-integration`, L41): *«leer cabecera real de cada archivo antes de
  parsear; cualquier cambio de columnas/orden ⇒ nueva schema_version + transformador adaptado con
  test, jamás asumir columnas fijas»*.

## 2. Decisiones de diseño

| # | Decisión | Razón |
|---|---|---|
| D1 | El schema se **detecta del header real** de cada `.csv.gz` (`detect_source_schema` / `read_source_schema`), no de la fecha ni del manifiesto | jamás asumir columnas fijas |
| D2 | Dos schemas explícitos y cerrados: `SOURCE_SCHEMA_V1="bybit-spot-trades-csv-gz-v1"` (5 col) y `SOURCE_SCHEMA_V2="bybit-spot-trades-csv-gz-v2"` (6 col con `rpi` final) | contrato auditable; V1 conserva el valor de `BRONZE_SCHEMA_VERSION` existente |
| D3 | `rpi` **no se propaga ni se reinterpreta**: Silver valida el ancho contra el schema detectado, lee `row[:5]` y emite siempre las mismas 10 columnas canónicas | salida Silver idéntica para V1 y V2 |
| D4 | Cualquier otro header u orden ⇒ `SourceSchemaError` (Bronze) / `InvalidRowError` (Silver) — FAIL CLOSED en descarga, backfill y transform | regla 3 del enunciado |
| D5 | `schema_version` **por archivo** del manifest Bronze = schema de la fuente detectado; el `schema_version` **del manifiesto** sigue siendo `bybit-spot-trades-csv-gz-v1` (compatibilidad del manifiesto, no del raw) | no rompe verificadores M9-A ni la descarga existente |
| D6 | Silver registra `source_schema_version` en su entrada (linaje) | regla 7 |
| D7 | `transform_day` rechaza si el `schema_version` del manifiesto Bronze **contradice** al archivo detectado (`HashConflictError`) | fuerza el backfill antes de transformar y deja el FAIL CLOSED explícito |
| D8 | Backfill determinista y atómico: solo reescribe el manifest si algo cambió (mismo formato `sort_keys+indent=2`), verifica SHA-256 de cada raw, **nunca** toca `.csv.gz`, y solo appendea `ops-*` cuando hubo cambio | reglas 4-5 |

## 3. TDD (RED → GREEN)

1. **RED**: `tests/test_source_schema.py` (43 tests) + ajustes en `test_silver_trades.py` y
   `test_bronze_ingest.py` → `ImportError` inicial (módulo/funciones aún inexistentes).
2. **GREEN**: implementación mínima en `bronze.py`, `silver.py` + nuevo
   `schema_backfill_cli.py`.
3. Dos tests preexistentes adaptados a propósito (su intención se mantiene):
   - `test_wrong_header_fail_closed` instala el archivo a mano (`install_bronze_body`) porque
     ahora **la descarga** ya rechaza headers desconocidos (el guard de transform sigue cubierto).
   - `test_hash_conflict_fails_closed` usa payloads CSV válidos (antes `contenido A/B\n` que ya no
     pasaría la validación de schema en la descarga).

## 4. Ejecución (evidencia en `docs/phases/23/evidence/`)

| Paso | Artefacto | Resultado |
|---|---|---|
| 01 unit tests medallion | `m9a1-01-unit-tests-medallion.log` | PASS — 262 tests, cobertura medallion **93.71%** (≥90) |
| 01b unit tests medallion | `m9a1-01b-unit-tests-medallion.log` | **PASS** — 272 tests, cobertura **94.60%** (bronze 97%, silver 95%, schema_backfill_cli 94%) |
| 02 suite completa | `m9a1-02-unit-tests-full.log` | PASS (exit=0) |
| 02b suite con conteo | `m9a1-02b-unit-tests-full-count.log` | **PASS — 1227 passed, 1 skipped** (`tests --ignore=tests/integration`) |
| 03 lint/typing | `m9a1-03-lint-typing.log` | **PASS** — `ruff check .` + `ruff format --check .` + `mypy src tests` (287 files, strict) |
| 04 deploy | `m9a1-04-deploy.log` | PASS — HEAD = base sin commits; `tar\|ssh` → `/tmp/m9a/src`; detección sobre archivos REALES: `2023-09-09→V1`, `2025-03-13→V2` |
| 05 snapshot before | `m9a1-05-snapshot-before.log` | PASS — 647 raw (3,1G) + 551 salidas (4,1G) hasheados; histograma `{'v1':551,'v2':96}`; linaje Silver `{'ABSENT':551}`; header canónico 10 cols |
| 05b baseline downstream | `m9a1-05b-downstream-baseline.log` | PASS — 3 hashes base (candles manifest, gold manifest, replay-config) |
| 06 FAIL CLOSED pre-backfill | `m9a1-06-failclosed-pre-backfill.log` | **PASS** — `exit=1` con `schema_version manifest '…-v1' != detectado '…-v2' (metadata Bronze sin backfill)`; sin output parcial, 0 `.part`, 551 salidas intactas |
| 07 backfill | `m9a1-07-backfill.log` | **PASS** — `BRONZE_V1_FILES=551`, `BRONZE_V2_FILES=96`, `BRONZE_ENTRIES_CHANGED=96`, `SILVER_ENTRIES_CHANGED=551`; 2ª corrida idempotente (`CHANGED=0`) |
| 08 UAT transform | `m9a1-08-transform-2025-03-13.log` | **PASS** — `transformed=1`, 691 556 filas (1:1 con Bronze), `source_schema_version=…-v2`, header canónico 10 col sin `rpi`, orden canónico, 0 `.part` |
| 09 verificación integridad | `m9a1-09-verify-integrity.log` | **PASS** — `BRONZE_RAW_HASHES_CHANGED=0` · `EXISTING_SILVER_HASHES_CHANGED=0` · diff del manifest Bronze **solo** claves `schema_version` (96) · 551 entradas Silver solo ganaron `source_schema_version` · candles/gold intactos |
| 10 smoke V2 | `m9a1-10-smoke-v2.log` | **PASS** — 3 fechas más (`2025-03-14`, `2025-03-15`, `2025-06-16`) → `transformed=3`; 551 preexistentes **0 changed**; 555 entradas con linaje |
| 11 estado final | `m9a1-11-final-state.log` | **PASS** — `BRONZE=647/647`, `SILVER=555`, `CANDLES=21`, `GOLD untouched`, `PART_FILES_TOTAL=0`, histogramas `bronze{551,96}` / `silver{551,4}`, contenedores sin tocar |

## 5. SALIDA (M9-A1)

```
MEDALLION_M9A1=PASS
BRONZE_V1_FILES=551
BRONZE_V2_FILES=96
BRONZE_RAW_HASHES_CHANGED=0
BRONZE_ENTRIES_SCHEMA_CHANGED=96
SILVER_ENTRIES_BACKFILLED=551
SILVER_CANONICAL_SCHEMA_CHANGED=0
EXISTING_551_SILVER_HASHES_CHANGED=0
TRANSFORMED_2025_03_13=YES (rows=691556, source_schema_version=bybit-spot-trades-csv-gz-v2)
V2_SMOKE_TEST=PASS (2025-03-14, 2025-03-15, 2025-06-16 → transformed=3)
UNKNOWN_SCHEMA_FAIL_CLOSED=PASS (exit=1 pre-backfill + tests unit)
READY_FOR_COMMIT=YES
READY_TO_RESUME_M9A=YES (92 días V2 pendientes, NO ejecutados)
```

## 6. Qué se implementó

| Archivo | Rol |
|---|---|
| `src/infrastructure/medallion/bronze.py` | Constantes `SOURCE_SCHEMA_V1/V2`, `BRONZE_HEADER_V1/V2`, `SOURCE_HEADERS`; `SourceSchemaError`; `detect_source_schema()`; `read_source_schema()`; `download_day` valida gzip **y** header real (registra el schema detectado; limpia `.part` y directorio vacío si falla); `SchemaBackfillResult` + `backfill_source_schema()` |
| `src/infrastructure/medallion/silver.py` | `_read_bronze_rows` detecta el schema, valida el ancho contra él y devuelve el schema; `transform_day` cruza contra el manifest (D7) y escribe `source_schema_version`; `SilverSchemaBackfillResult` + `backfill_source_schema()` (verifica linaje, no escribe `.csv.gz`) |
| `src/infrastructure/medallion/schema_backfill_cli.py` | CLI stdlib `--bronze-dir --dest-dir --symbol --layer {all,bronze,silver} --require-marker`; imprime `BRONZE_*` / `SILVER_*`; exit 0/1/2 |
| `tests/test_source_schema.py` | 43 tests nuevos (detección, descarga, transform V2, `rpi`, backfill×2, manifiestos mal formados, CLI) |
| `tests/test_silver_trades.py` | `install_bronze_body` + test de header desconocido reorientado; `BRONZE_SCHEMA_VERSION` importado |
| `tests/test_bronze_ingest.py` | payloads válidos en `test_hash_conflict_fails_closed` (intención intacta) |

## 7. Tests (43 nuevos en `tests/test_source_schema.py`)

Detección V1/V2 · 6 headers desconocidos/reordenados/vacíos FAIL CLOSED · lectura de schema desde
gzip (y rechazo de vacío/no-gzip) · descarga registra V1 y V2 por archivo · descarga con header
desconocido FAIL CLOSED (sin `.part`, sin manifiesto) · transform V2 con linaje `source_schema_version`
· transform con manifiesto que contradice al archivo (D7) · transform con header desconocido ·
**`rpi` no propagado** (mismas 5 columnas de datos ⇒ filas idénticas salvo el sha de linaje, y el
centinela `424242` no aparece) · fila V2 con ancho 5 FAIL CLOSED · hash de salida V2 determinista ·
backfill Bronze (cuenta 551/96, corrige solo `schema_version`, raw intacto, idempotente, noop si ya
está correcto, header desconocido/raw alterado/raw ausente/fuera de split FAIL CLOSED) · backfill
Silver (551 ganan `source_schema_version` sin reescribir salidas, idempotente, header desconocido,
linaje alterado, path traversal, entrada incompleta/fecha inválida/fuera de split FAIL CLOSED) ·
transform con Bronze vacío o solo-header FAIL CLOSED · CLI (`all`, `--layer bronze`, marker,
FAIL CLOSED, `--layer` inválido).

## 8. Cumplimiento de las reglas M9-A1

1. Detectar header real por archivo (V1/V2) — **PASS** (D1 + tests + `m9a1-04`, `m9a1-05`)
2. `rpi` no reinterpretable ni propagable; salida canónica idéntica — **PASS** (D3 + test centinela + `m9a1-08`)
3. Cualquier otro header/orden ⇒ FAIL CLOSED — **PASS** (D4 + `m9a1-06` + tests)
4. NO tocar los 647 `.csv.gz` — **PASS** (`BRONZE_RAW_HASHES_CHANGED=0`)
5. Metadata Bronze determinista/atómica `V1_FILES=551`, `V2_FILES=96` — **PASS** (`m9a1-07`)
6. Silver con `source_schema_version` en linaje — **PASS** (551 backfilled + 4 nuevos)
7. Backfill de los 551 sin reescribir salidas — **PASS** (`EXISTING_551_SILVER_HASHES_CHANGED=0`)
8. `ordering_fidelity=PARTIAL` y `source_row_number` preservado — **PASS** (555/555 `PARTIAL`)
9. UAT: solo `2025-03-13` + pocas fechas V2, sin bulk — **PASS** (`m9a1-08`, `m9a1-10`)
10. Evidencia + doc creadas; sin commit/push — **PASS** (HEAD = base)

## 9. Pendiente (M9-B, NO ejecutado)

- Transformar los **92 días V2 restantes** (96 − 4 ya transformados) con el mismo pipeline.
- Candles (`21` outputs) y gold (manifest intacto) no se tocaron; `replay` no se corrió.
- Tras el commit autorizado: re-indexar el grafo (`index_repository`) y verificar cobertura
  (`check_index_coverage`) sobre `bronze.py`, `silver.py`, `schema_backfill_cli.py` y los tests.

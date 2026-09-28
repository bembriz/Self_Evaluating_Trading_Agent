# M4 — Silver Canonical Trades

**Fecha:** 2026-09-27 (UTC-6) / 2026-09-28 (UTC en lenovosrv)
**Rama:** `medalion` @ `cc6d75f22588ffeee0a058ae8e449ac409d890cb` (precondición verificada)
**Alcance:** transformar SOLO los 3 días Bronze existentes a Silver trades canónicos,
deterministas, auditables e idempotentes en `/srv/data/medallion/silver/trades/ETHUSDT/`.
**Gate:** instrucción directa del usuario (M4). Restricciones: NO commit, NO push, NO bulk.

## Análisis previo de la fuente (`m4-01`)

- Schema REAL (confirmado en los 3 archivos): `id,timestamp,price,volume,side`
- Filas: 402 114 + 572 158 + 906 521 = **1 880 793** (GRAND_ROWS)
- `sides` = {buy, sell} únicamente · ids/timestamps enteros puros · precios/cantidades
  decimales canónicos (`^[0-9]+(\.[0-9]+)?$`), 0 filas inválidas
- **0 inversiones de timestamp y 0 de id** en los 3 días ⇒ fuente ordenada
  (timestamp no decreciente, id nativo no decreciente)
- Duplicados legítimos `(ts,price,qty,side)`: 47 420 / 49 476 / 80 751 → DEBEN preservarse
- SHA-256 Bronze verificado contra manifest en cada archivo

## Ejecución (evidencia en `docs/phases/23/evidence/`)

| Paso | Artefacto | Resultado |
|---|---|---|
| 01 análisis fuente | `m4-01-bronze-analysis.log` | PASS — schema/orden/lados/duplicados (arriba) |
| 02 unit tests | `m4-02-unit-tests.log` | exit=1 — `test_cli_rejects_walk_forward_date`: `transform_days` pre-creaba el destino ANTES del split guard (corregido: mkdir solo tras el guard) |
| 02b unit tests | `m4-02b-unit-tests.log` | **PASS** — 30+28 tests silver+bronze; cobertura medallion **92.32%** (silver 91%, silver_cli 90%) |
| 03 repo quality | `m4-03-repo-quality.log` | **PASS** — `ruff check .` + `ruff format --check .` + `mypy src tests` (273 files) + `pytest tests --ignore=tests/integration` → **1013 passed, 1 skipped** |
| 04 preflight lenovosrv | `m4-04-preflight.log` | PASS — marker ✓, Bronze intacto (3+manifest), Silver destino AUSENTE, Python 3.12.3, baseline contenedores intacta |
| 05 deploy copy | `m4-05-deploy-copy.log` | PASS — `tar\|ssh` → `/tmp/m4/src`; `IMPORT_OK`; CLI `--help` OK (stdlib, sin venv) |
| 06 UAT RUN1 | `m4-06-uat-run1.log` | **PASS** — `transformed=3`; row counts idénticos; lineage/orden OK |
| 07 UAT RUN2 | `m4-07-uat-run2.log` | **PASS** — `transformed=0 skipped=3`; hashes y manifest byte-idénticos; 0 `.part` |
| 08 UAT negative | `m4-08-uat-negative.log` | **PASS** — WF/holdout/pre-DEV → exit 1 sin crear particiones; fecha mala → 2; marker ausente → 1 |
| 09 precommit local | `m4-09-precommit.log` | PASS — 58 tests silver+bronze antes del candidate |
| 10 corrección calidad | `m4-10-correction-quality.log` | **PASS** — ruff+format+mypy + 58 tests (capa medallion 92.42%) + suite **1013 passed, 1 skipped** |
| 11 regeneración manifest | `m4-11-manifest-regeneration.log` | **PASS** — código PARTIAL desplegado; backup; re-transform 3 días → hashes idénticos al RUN1 (`OUTPUT_DATA_HASH_CHANGED=NO`); manifest `FULL→PARTIAL` + `source_order_preserved:true` (`MANIFEST_HASH_CHANGED=YES`); `SILVER_ROWS=1880793` |
| 12 RUN2 revalidación | `m4-12-run2-revalidation.log` | **PASS** — `transformed=0 skipped=3`; outputs+manifest estables; 0 `.part`; 3 particiones; linaje PASS; WF guard exit 1, `WF_READS_DELTA=0` |

> El intento fallido m4-02 queda registrado a propósito: el guard se movió al inicio de
> `transform_day` (defensa en profundidad, antes de crear el árbol destino).

## Qué se implementó

| Archivo | Rol |
|---|---|
| `src/infrastructure/medallion/silver.py` | `transform_day(silver_dir…)` — split guard → hash Bronze vs manifest → lectura/validación total de filas (FAIL CLOSED ante la primera inválida, sin crear output) → orden canónico `(event_timestamp, source_row_number)` → escritura gzip determinista `.part` (mtime=0, sin FNAME, LF, UTF-8) → round-trip count → manifest atómico determinista → `os.replace` → ops log separado |
| `src/infrastructure/medallion/silver_cli.py` | CLI stdlib: `--bronze-dir --dest-dir --symbol --dates --require-marker`; `SUMMARY transformed=N skipped=M`; exit 0/1/2 |
| `tests/test_silver_trades.py` | 28 unit tests sin red (lista completa abajo) |

### Schema canónico de salida (10 columnas)

`event_timestamp,symbol,price,quantity,taker_side,native_trade_id,native_sequence,source_file,source_file_sha256,source_row_number`

- `native_sequence` vacío: el schema real NO tiene columna de secuencia (no se asumen columnas);
  `native_trade_id` = `id` de origen.
- `price`/`quantity`: validados como **Decimal** (regex canónico, nunca float) y emitidos
  **byte-a-byte como en el origen** → precisión exacta garantizada.
- **Sin dedupe**: unicidad solo por `(source_file, source_row_number)`.
- Linaje por fila: `source_file` = `date=…/ETHUSDT_….csv.gz` + SHA-256 del Bronze + número de fila.

### ORDERING_FIDELITY = PARTIAL + SOURCE_ORDER_PRESERVED (corregido)

- Regla total declarada: `(event_timestamp, source_row_number)`; `source_row_number`
  preserva exactamente el orden físico publicado por Bybit (cálculo por partición en
  `source_order_preserved`).
- El archivo Spot histórico **NO contiene `native_sequence`/cross-sequence** ⇒ con
  timestamps repetidos no es demostrable el orden del matching engine ⇒
  `ORDERING_FIDELITY=PARTIAL` (regla de la skill; corrección aplicada en
  `m4-10`…`m4-12` tras instrucción del usuario; el manifest previo `FULL` de los 3 días
  se regeneró con `m4-11`).
- `SOURCE_ORDER_PRESERVED=YES`: verificado en los 3 días (`m4-01`: 0 inversiones de
  timestamp) y registrado por partición en el manifest
  (`source_order_preserved: true` — calculado en cada transform, no constante global).

### Manifest Silver (por partición, determinista)

`source_bronze_path`, `source_bronze_sha256`, `output_path`, `output_sha256`, `row_count`,
`min_timestamp`, `max_timestamp`, `schema_version` (`bybit-spot-trades-silver-v1`),
`ordering_fidelity` (`PARTIAL`), `source_order_preserved`, `symbol`, `date` — claves
ordenadas, sin timestamps de ejecución (ops → `ops-transforms.jsonl` aparte).

## UAT en lenovosrv

- RUN1: `transformed=3` en `/srv/data/medallion/silver/trades/ETHUSDT/date=2024-06-0{1,2,3}/`
- **SOURCE_ROWS = SILVER_ROWS = 1 880 793** (`ROW_COUNT_MATCH=YES`; dedupe habría perdido filas)
- Lineage OK en los 3 días (manifest Silver ↔ Bronze hash idéntico; muestra de fila con
  `source_file`+sha+nº de fila); orden monótono verificado leyendo cada output completo
- RUN2: `skipped=3` → **0 changed** (mismos SHA-256 + manifest `cmp` idéntico; 0 `.part`)
- Salidas: `c98549d053e8…`, `241b5704c848…`, `45ecb3bfa4bb…`
- Negative: `WF_READS=0`, `HOLDOUT_READS=0` — 0 particiones fuera de DEVELOPMENT
- **Corrección de fidelidad (`m4-10`…`m4-12`)**: `FULL→PARTIAL` + `source_order_preserved`;
  los CSV.gz NO cambiaron (mismos SHA-256: `c98549d053e8…`, `241b5704c848…`,
  `45ecb3bfa4bb…`; `OUTPUT_DATA_HASH_CHANGED=NO`), solo el manifest
  (`MANIFEST_HASH_CHANGED=YES`); RUN2 tras la corrección → `skipped=3`, 0 changed

## Tests (28, `tests/test_silver_trades.py`)

transformación válida (columnas+linaje+manifest) · precisión Decimal byte-a-byte
(0.00000001, 17 decimales, sin `e-0`) · orden determinista con filas desordenadas ·
duplicados legítimos preservados (mismo id, distinta fila origen) · fila inválida
fail-closed ×8 variantes (lado/price/id/timestamp/exponencial/columnas faltantes/header) ·
Bronze hash mismatch · Bronze sin manifest · `.part` stale recuperado · RUN2 idempotente ·
output hash determinista entre dirs distintos · output Silver alterado · split guard
DEVELOPMENT (WF/holdout/pre-DEV, nada creado) · CLI (2 días + rerun + WF + fecha mala +
marker) · `transform_days` multi-día.

## Condiciones de la regla M4 (post-ejecución)

1. Solo los 3 días Bronze existentes; NO bulk — PASS
2. Decimal (no float) y sin dedupe — PASS
3. Orden total documentado; `ORDERING_FIDELITY=PARTIAL` + `SOURCE_ORDER_PRESERVED=YES` — PASS (corregido en `m4-10`…`m4-12`)
4. Bronze hash vs manifest guard — PASS (`m4-01`, RUN1, tests)
5. Fila inválida ⇒ FAIL CLOSED sin output parcial — PASS (tests)
6. `.part` + rename atómico + output determinista (misma entrada ⇒ mismo SHA-256) — PASS
7. Manifest Silver por partición con linaje completo — PASS (RUN1 verificación)
8. RUN1 3 particiones / RUN2 0 changed; filas Silver == filas Bronze — PASS
9. `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0` — PASS (`m4-08`)
10. Evidencia + doc creadas — PASS

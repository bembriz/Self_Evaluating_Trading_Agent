# M6 — Gold Replay Dataset

**Fecha:** 2026-09-28 (UTC-6)
**Rama:** `medalion` @ `37cd798a64f359ebde49cb2decce6689666746be` (precondición verificada)
**Alcance:** dataset Gold inmutable y reproducible para replay que **referencia**
Silver trades + candles sin copiar datos — solo 2024-06-01/02/03.
**Destino:** `/srv/data/medallion/gold/replay-datasets/ETHUSDT/<dataset_id>/`
**Gate:** instrucción directa del usuario (M6). Restricciones: NO commit, NO push,
NO bulk, NO WF, NO holdout.

## Qué se implementó

| Archivo | Rol |
|---|---|
| `src/infrastructure/medallion/gold.py` | `create_dataset` — split guard → validación total (hashes Silver + linaje candles→trades) → `dataset_id` content-addressed → escritura `.part` + round-trip + rename atómico; SKIP si idéntico, FAIL CLOSED si distinto |
| `src/infrastructure/medallion/gold_cli.py` | CLI stdlib: `--trades-dir --candles-dir --dest-dir --symbol --dates --require-marker`; exit 0/1/2 |
| `tests/test_gold_dataset.py` | 40 unit tests sin red (TDD: RED observado → GREEN) |

### `dataset_id` determinista (content-addressed)

`gold-replay-` + SHA-256 de un **canonical identity payload** sin campos variables:

```text
symbol · dates · trades_schema_version · candles_schema_version
ordering_fidelity · source_order_preserved
trade_partitions[{date,path,sha256,row_count}]  ×3
candle_outputs[{date,timeframe,path,sha256,candle_count}] ×21
replay_config (entero)
```

Canonical JSON: `sort_keys=True, indent=2, ensure_ascii=True` + `\n`. Mismo
contenido ⇒ mismo id (probado entre árboles distintos y orden de fechas invertido);
cualquier cambio de insumo o config ⇒ nuevo id (nuevo experimento, §4.9 PRD).

### Manifest (`manifest_version = gold-replay-dataset-v1`)

Campos mínimos exigidos por el gate, todos presentes:
`dataset_id`, `symbol`, `date_range`, `dates`, `allowed_split=DEVELOPMENT`,
`timeframes`, `source_roots`, `trades{schema_version, ordering_fidelity=PARTIAL,
source_order_preserved, partitions×3}`, `candles{schema_version, outputs×21,
candle_count_by_timeframe}`, `lineage{verified, rule, refs}`,
`replay_config{filename, sha256}`.

### `replay-config.json` (`replay-config-v1`)

Fija: `decision_timeframe=15m`, `context_timeframes=[1h,4h]`,
`execution_source=silver_trades`, `execution_model=TRADE_SEQUENCE_TAKER_PROXY`,
`candle_visibility=confirmed_close_only`, `decision_rule` (decisión **después** del
close confirmado), `fill_rule` (primer trade elegible desde el timestamp de
decisión), `limitations` (bid/ask, depth, queue, market impact, latencia —
**NO** modelados), `strategy_params_included=false`, `risk_params_included=false`
(config separado de estrategia/riesgo).

### Guards (FAIL CLOSED)

1. Split guard DEVELOPMENT **antes** de leer nada (`WALK_FORWARD_READS=0`,
   `FINAL_HOLDOUT_READS=0`).
2. `schema_version` de ambos manifests Silver.
3. Partición/celda ausente (entrada o archivo) ⇒ FAIL.
4. Hash de **cada** trades/candle recalculado vs manifest (`InputHashMismatchError`).
5. **Linaje**: `candles.source_trades == (path, sha256)` de la partición de su día
   (`LineageMismatchError`).
6. `ordering_fidelity ∈ {FULL, PARTIAL}` uniforme; `source_order_preserved` bool.
7. Sin wall-clock en `manifest.json`/`replay-config.json`; timestamps solo en
   `ops-gold.jsonl` (log separado, fuera del directorio del dataset).
8. `.part` + round-trip + rename atómico; stale `.part` limpiado;
   id existente con contenido distinto ⇒ `DatasetConflictError`.

## Ejecución (evidencia en `docs/phases/23/evidence/`)

| Paso | Artefacto | Resultado |
|---|---|---|
| 01 unit + coverage | `m6-01-unit-tests.log` | **PASS** — ruff/format/mypy + **163 tests** medallion; capa **96.11%** (gold.py **100%** branch/statement, gold_cli 96%) |
| 02 repo quality | `m6-02-repo-quality.log` | **PASS** — suite completa **1107 passed, 1 skipped** |
| 03 preflight | `m6-03-preflight.log` (intento con bug de script, exit 1) + `m6-03-preflight-ok.log` | **PASS** — HEAD `37cd798`, marker ✓, trades 3 (1 880 793) + candles 21 ✓, fidelity PARTIAL, gold dest AUSENTE, Bronze 3, Python 3.12.3 |
| 04 deploy copy | `m6-04-deploy-copy.log` | PASS — → `/tmp/m6/src`; `IMPORT_OK`; id determinista en import; CLI `--help` OK |
| 05 UAT RUN1 | `m6-05-uat-run1.log` | **PASS** — `CREATED … trades=3 candles=21`, `SUMMARY created=1 skipped=0`; solo `manifest.json` + `replay-config.json`; 0 `.part` |
| 06 RUN2 + determinismo | `m6-06-uat-run2-determinism.log` | **PASS** — `SKIPPED` mismo id, `RUN2_CHANGED=0`, manifest/config estables; destino fresco ⇒ **mismo id** + bytes idénticos (`DATASET_ID_DETERMINISTIC=YES`, `REPLAY_CONFIG_DETERMINISTIC=YES`); ops 2 eventos fuera del dataset |
| 07 verificación independiente | `m6-07-uat-verify.log` | **PASS** — 3 trades + 21 candles referenciados con hashes recalculados OK; `LINEAGE_VALIDATION=PASS`; config OK; **dataset_id recomputado = dir**; `NO_WALL_CLOCK=YES`; `SILVER_UNTOUCHED=YES`; `BRONZE_UNTOUCHED=YES` |
| 08 negatives | `m6-08-uat-negative.log` | **PASS** — split guard antes de leer (WF/holdout/pre-DEV exit 1, dirs inexistentes); fecha 2; marker 1; sandbox hash/linaje/partición ⇒ exit 1 FAIL CLOSED sin crear destino; canónico intacto; `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0` |

## Resultados UAT (lenovosrv)

- **DATASET_ID** = `gold-replay-a8c49e0be9154194841a97c4f26225a76cef9fba8d9a6d080198359c124ebdc3`
- `manifest.json` sha256 = `9411a4e01a5adccbb448df062f0eca857213e8259441535b5812ee4688af99df`
- `replay-config.json` sha256 = `be8aae2df45670e1f987ab11e68f1471d0cb89104c0e53483d2d0de90fa18314`
- Referencias: **3** Silver trade partitions (402 114 + 572 158 + 906 521 = 1 880 793
  filas) + **21** candle outputs (7 timeframes × 3 días)
- `candle_count_by_timeframe`: `1m:4320, 5m:864, 15m:288, 30m:144, 1h:72, 4h:18, 1d:3`
- RUN1 `created=1` → RUN2 `skipped=1` (**0 cambios**) → destino fresco con mismo id y
  bytes idénticos (determinismo total)
- Silver y Bronze verificados byte-a-byte tras la ejecución (intactos)

## Tests (40 casos, `tests/test_gold_dataset.py`)

dataset_id determinista entre árboles/orden de fechas · id cambia con contenido ·
canonical JSON byte-idéntico · `compute_dataset_id` = sha del canonical ·
hash mismatch trades/candles ⇒ FAIL · linaje mismatch ⇒ FAIL · partición ausente
(archivo/entrada/trades/candles/manifest) ⇒ FAIL · rerun SKIP idempotente ·
dataset existente alterado ⇒ FAIL CLOSED · dir inmutable por rerun · split guard
WF **y** holdout antes de leer · manifest con campos mínimos · 3+21 referencias con
hash verificado · sin wall-clock · ops fuera del dataset · replay config completo ·
CLI created/skip/fecha/marker/guard · ramas de error (manifest ilegible/estructura,
schema mismatch, fidelity inválida/mixta, sop inválido, row/candle_count inválido,
sha inválido, días vacíos, round-trip fallido limpia `.part`, `.part` stale
eliminado).

## Condiciones de la regla M6 (post-ejecución)

1. Solo 2024-06-01/02/03; NO bulk; NO WF; NO holdout — PASS (`m6-05/06/08`)
2. Todos los hashes validados antes de crear Gold — PASS (`m6-01/05/07/08`)
3. Linaje candles → Silver validado — PASS (`m6-07`, `m6-08`)
4. FAIL CLOSED ante missing/hash/lineage mismatch — PASS (`m6-01`, `m6-08`)
5. Sin wall-clock en archivos deterministas; ops en log separado — PASS (`m6-07`)
6. `.part` + rename atómico — PASS (`m6-01/05`)
7. Dataset idéntico ⇒ SKIP; id con contenido distinto ⇒ FAIL — PASS (`m6-06`, `m6-01`)
8. dataset_id determinista + config determinista — PASS (`m6-06`, `m6-07`)
9. Evidencia `m6-*` + doc creadas — PASS

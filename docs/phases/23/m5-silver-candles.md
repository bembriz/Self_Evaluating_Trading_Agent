# M5 — Silver Candles Multi-Timeframe

**Fecha:** 2026-09-28 (UTC-6)
**Rama:** `medalion` @ `d2aef304239df55d7b20dcd740ae898d6c5b90ac` (precondición verificada)
**Alcance:** generar candles deterministas SOLO desde Silver trades para los 3 días
DEVELOPMENT existentes (2024-06-01/02/03) en
`/srv/data/medallion/silver/candles/ETHUSDT/`.
**Gate:** instrucción directa del usuario (M5). Restricciones: NO commit, NO push, NO bulk.

## Qué se implementó

| Archivo | Rol |
|---|---|
| `src/infrastructure/medallion/candles.py` | `transform_day/transform_days` — split guard → validación de hashes Silver (manifest + row_count) → lectura/validación total de filas (FAIL CLOSED) → agregación OHLCV por ventana calendario UTC → gzip determinista `.part` → round-trip → manifest atómico → rename → ops log |
| `src/infrastructure/medallion/candles_cli.py` | CLI stdlib: `--trades-dir --dest-dir --symbol --dates --require-marker`; exit 0/1/2 |
| `tests/test_silver_candles.py` | 45 funciones de test (54 casos con parametrización) sin red |

### Semántica (reglas M5)

- **UTC** puro; intervalos **`[open_time, close_time)`** con `close_time = open_time + duration`.
- **7 timeframes:** `1m 5m 15m 30m 1h 4h 1d` — todos dividen 86 400 000 ms ⇒ ninguna
  vela cruza la frontera del archivo diario fuente (4h/1d alineados a medianoche UTC).
- **OHLC** según el orden canónico de Silver `(event_timestamp, source_row_number)`:
  `open` = primera operación, `close` = última, `high`/`low` por comparación `Decimal`
  exacta (desempate en la primera aparición ⇒ determinista). Precios preservados
  **byte-a-byte** del origen (nunca float).
- **`volume`** = suma `Decimal` exacta en notación fija (`format(d, "f")`); **`trade_count`**
  = número de operaciones de la vela.
- **Sin gap filling / velas sintéticas:** solo se emiten buckets con ≥1 operación.
- **Velas confirmadas:** toda vela emitida está cerrada dentro del día completo de la
  fuente (`close_time <= fin del día`) — fuente histórica congelada completa.
- **Mismo input ⇒ mismo SHA-256** (gzip mtime=0, sin FNAME, LF, UTF-8, claves ordenadas).

### Schema canónico de salida (10 columnas)

`open_time,close_time,symbol,timeframe,open,high,low,close,volume,trade_count`

### Layout y manifest

- Output: `candles/ETHUSDT/timeframe=<tf>/date=<día>/ETHUSDT_<día>_<tf>.csv.gz`
- Manifest único por símbolo (`manifest.json`, determinista), entrada por output con:
  `timeframe`, **`source_trades: [{path, sha256}]`** (linaje Silver), `output_sha256`,
  `candle_count`, `min_open_time`, `max_open_time`, `duration_ms`, `schema_version`
  (`bybit-spot-candles-silver-v1`), `symbol`, `date`, `output_path`, `filename`.
- Ops log separado: `ops-candles.jsonl` (sin timestamps en el manifest).

### Guards

1. Split guard DEVELOPMENT **antes** de leer nada (probado con `--trades-dir`
   inexistente: el error es el guard, no la fuente).
2. Hash del trades Silver contra su manifest + `row_count` (FAIL CLOSED).
3. Fila inválida (header/columnas/regex/símbolo/fuera de día/orden canónico violado)
   ⇒ FAIL CLOSED **sin crear el árbol destino**.
4. `.part` + round-trip + manifest atómico + `os.replace`; `.part` limpiado en fallo.
5. Rerun: output existente ⇒ hash + linaje verificados ⇒ `skipped` (sin reescribir
   manifest ni outputs).
6. No se lee ni se escribe Bronze (verificado post-UAT: hashes Bronze intactos).

## Ejecución (evidencia en `docs/phases/23/evidence/`)

| Paso | Artefacto | Resultado |
|---|---|---|
| 01 unit + coverage | `m5-01-unit-tests.log` | **PASS** — ruff/format/mypy + 112 tests (candles+silver+bronze); capa medallion **95.10%** (candles.py **100%** branch/statement, candles_cli 94%) |
| 02 repo quality | `m5-02-repo-quality.log` | **PASS** — ruff+format+mypy (279 files) + suite completa **1067 passed, 1 skipped** |
| 03 preflight | `m5-03-preflight.log` | PASS — marker ✓, fuente Silver 1 880 793 filas + hashes + PARTIAL ✓, destino candles AUSENTE, Bronze 3 ✓, Python 3.12.3 |
| 04 deploy copy | `m5-04-deploy-copy.log` | PASS — `tar\|ssh` → `/tmp/m5/src`; `IMPORT_OK`; CLI `--help` OK |
| 05 UAT RUN1 | `m5-05-uat-run1.log` | **PASS** — `SUMMARY transformed=21 skipped=0 total=21` (7 tf × 3 días); 0 `.part`; solo DEVELOPMENT |
| 06 validación independiente | `m5-06-ohlc-validation.log` | **PASS** — recomputo completo independiente (sin importar `candles`): OHLC/volume/count **0 mismatches**, `UTC_BOUNDARIES=PASS`, `SYNTHETIC_CANDLES=0`, `SILVER_HASH_GUARD=PASS`, suma `trade_count` = 1 880 793 en TODOS los tf |
| 07 RUN2 + determinismo | `m5-07-uat-run2-determinism.log` | **PASS** — `transformed=0 skipped=21`, `RUN2_CHANGED=0`, manifest estable; dir fresco ⇒ mismos 21 hashes (`OUTPUT_HASH_DETERMINISTIC=YES`) + manifest idéntico |
| 08 negatives | `m5-08-uat-negative.log` | **PASS** — WF/holdout/pre-DEV exit 1 con mensaje del guard ANTES de leer (fuente inexistente); fecha mala 2; marker 1; sandbox trades alterado → exit 1 `hash mismatch`, sin outputs; `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0` |
| 09 Bronze intacto | `m5-09-bronze-untouched.log` | **PASS** — 3 hashes Bronze idénticos al manifest; contenedores `running` (baseline) |

## UAT en lenovosrv — resultados

- RUN1: 21 outputs → `/srv/data/medallion/silver/candles/ETHUSDT/timeframe=<tf>/date=2024-06-0{1,2,3}/`
- **CANDLES_BY_TIMEFRAME:** `1m:4320, 5m:864, 15m:288, 30m:144, 1h:72, 4h:18, 1d:3`
  (= 4320 minutos/día × 3 días ocupados; ETHUSDT tuvo trades en todos los minutos)
- Muestra (1m primer día): `['1717200000000','1717200060000','ETHUSDT','1m','3762.62','3766.5','3762.62','3765.96','49.89807','368']`
  — open = primera operación (`3762.62`, primera de 368 en el minuto)
- Validación independiente: OHLC/volume/count recalculados desde los trades crudos
  (gzip+csv+Decimal, sin importar el módulo `candles`) para los 21 outputs ⇒ **0 mismatches**
- RUN2: `skipped=21`, outputs y manifest byte-idénticos (0 changed); dir fresco ⇒
  mismos hashes (determinismo)

## Tests (54 casos, `tests/test_silver_candles.py`)

OHLC exacto · Decimal sin float (0.1+0.2=0.3) · límites UTC (open/close exclusivo) ·
primera/última operación definen open/close · volume + trade_count · sin gap filling ·
close == siguiente open (sin solapes) · hash mismatch / manifest sin entrada /
row_count divergente ⇒ FAIL CLOSED · 10 variantes de fila inválida (parametrizado) ·
archivo vacío/header-only/header incorrecto/columnas · symbol/timestamp fuera del día/
orden canónico violado · schema_version del manifest · archivo fuente ausente ·
row_count ausente · output sin entrada · linaje alterado · determinismo entre dirs ·
idempotencia RUN2 · output alterado · `.part` stale recuperado · fallo de escritura
limpia `.part` · split guard WF · guard de vela fuera de fuente · guards de
round-trip · agregación 4h con cruce de frontera (03:59:59.999 / 04:00:00.000) ·
4h solo buckets ocupados · 1d del día completo (close = fin de día) · manifest de
linaje completo · `transform_days` multi-día · CLI (éxito + rerun, WF, fecha mala,
token vacío, marker).

## Condiciones de la regla M5 (post-ejecución)

1. Solo 2024-06-01/02/03; NO bulk — PASS (`m5-05`, sin descargas nuevas)
2. UTC + `[open, close)` + OHLC por orden canónico — PASS (`m5-06`)
3. volume Decimal + trade_count, NO float — PASS (`m5-01`, `m5-06`)
4. Sin gap filling / velas sintéticas — PASS (`m5-06`: buckets == ocupados, `SYNTHETIC=0`)
5. Velas confirmadas con fuente histórica completa — PASS (close ≤ fin día en todos)
6. Mismo input ⇒ mismo SHA-256 — PASS (`m5-07` dir fresco)
7. Manifest con linaje completo (tf, source paths+hashes, output hash, candle_count,
   min/max open_time, schema_version) — PASS (`m5-01` test + `m5-05`/`m5-06`)
8. Hash Silver guard + DEVELOPMENT + FAIL CLOSED + `.part`/gzip determinista — PASS
   (`m5-08`, `m5-01`)
9. RUN1 21 outputs / RUN2 0 changed — PASS (`m5-05`, `m5-07`)
10. Validación OHLC/volume/count independiente — PASS (`m5-06`)
11. `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0` — PASS (`m5-08`)
12. No tocar Bronze — PASS (`m5-09`)
13. Evidencia + doc creadas — PASS

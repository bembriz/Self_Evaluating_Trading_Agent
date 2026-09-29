# Commit Candidate Report — 2026-09-28 (M9-A1)

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> **Estado: NO COMMIT** — pendiente de aprobación explícita del usuario.

## Objetivo

Registrar M9-A1 (Evolución de schema de la fuente Bybit Spot V1/V2 + backfill de metadata):
el pipeline Medallion deja de asumir columnas fijas y detecta el header **real** de cada
`.csv.gz` (`SOURCE_SCHEMA_V1` = 5 columnas, `SOURCE_SCHEMA_V2` = 6 columnas con `rpi` final);
`rpi` jamás se propaga ni se reinterpreta (la salida canónica Silver de 10 columnas es idéntica
para V1 y V2); cualquier otro header/orden ⇒ FAIL CLOSED en descarga, backfill y transform; el
manifest Bronze corrige `schema_version` por archivo de forma determinista/atómica
(551 V1 / 96 V2) sin tocar los 647 raw, Silver gana `source_schema_version` en el linaje de las
551 entradas existentes sin reescribir salidas, y el transform rechaza si la metadata
contradice al archivo (fuerza el backfill previo). UAT en lenovosrv sobre **solo `2025-03-13`**
+ 3 fechas V2 de humo; los 92 días V2 restantes quedan pendientes (M9-B).

## Rama

| Campo | Valor |
|---|---|
| branch | `medalion` |
| base commit | `dc5c0a2d791686e25a54661a81902a17564ef4b0` (= HEAD verificado en deploy y postcheck; `COMMITS_SIN_BASE=0`) |

## Archivos

- **Creados (4 + 14 evidencias):**
  - `src/infrastructure/medallion/schema_backfill_cli.py` — CLI stdlib de backfill
    (`--bronze-dir --dest-dir --symbol --layer {all,bronze,silver} --require-marker`;
    imprime `BRONZE_V1_FILES`/`BRONZE_V2_FILES`/`BRONZE_ENTRIES_CHANGED`/`SILVER_*`; exit 0/1/2)
  - `tests/test_source_schema.py` — 43 tests TDD (detección, descarga, transform V2, `rpi`,
    backfill×2, manifiestos mal formados, CLI)
  - `docs/phases/23/m9a1-bybit-schema-evolution.md` — doc de milestone
  - `docs/phases/23/commit-candidate-011.md` — este reporte
  - `docs/phases/23/evidence/m9a1-*.log` — **18 evidencias**: UAT
    (`01`, `01b`, `02`, `02b`, `03`, `04`, `05`, `05b`, `06`, `07`, `08`, `09`, `10`, `11`)
    + precommit (`12`, `12b`, `13`, `13b`; los intentos fallidos `12` y `13` quedan
    registrados por convención — `12` falló por un patrón de grep mal ubicado y `13`
    porque el assert de "Silver añadido" seguía esperando 1 fecha antes del smoke)
- **Modificados (5):**
  - `src/infrastructure/medallion/bronze.py` — constantes `SOURCE_SCHEMA_*`/`BRONZE_HEADER_V1|V2`,
    `SourceSchemaError`, `detect_source_schema`, `read_source_schema`, `download_day` valida el
    header real y lo registra, `SchemaBackfillResult` + `backfill_source_schema`
  - `src/infrastructure/medallion/silver.py` — detección de schema en `_read_bronze_rows` +
    ancho por schema + `source_schema_version` en linaje + cruce FAIL CLOSED contra el manifest
    + `SilverSchemaBackfillResult` + `backfill_source_schema`
  - `tests/test_silver_trades.py` — helper `install_bronze_body` y test de header desconocido
    reorientado al guard de transform
  - `tests/test_bronze_ingest.py` — payloads válidos en `test_hash_conflict_fails_closed`
  - `docs/phases/23/evidence/log.md` — índice de evidencias
- **Eliminados:** ninguno

## Diff

```bash
$ git diff --numstat          # tracked (incluye evidence/log.md)
36  0   docs/phases/23/evidence/log.md
133 3   src/infrastructure/medallion/bronze.py
115 13  src/infrastructure/medallion/silver.py
4   3   tests/test_bronze_ingest.py
36  3   tests/test_silver_trades.py
$ git diff --shortstat        # = 5 files changed, 324 insertions(+), 22 deletions(-)
$ wc -l (nuevos sin trackear)
69    src/infrastructure/medallion/schema_backfill_cli.py
801   tests/test_source_schema.py
131   docs/phases/23/m9a1-bybit-schema-evolution.md
$ git diff --check            # 0 hallazgos (diff de código)
```

> **Fuera de este candidate (sin commit, heredados de M9-A recovery):** 16 logs
> `docs/phases/23/evidence/m9a-*.log` + 14 logs `m9a-recovery-*.log`. Incluirlos queda a
> criterio del usuario; el resto del worktree es solo este M9-A1.

## Arquitectura afectada

- **Capa Bronze** (`bronze.py`): contrato de metadata por archivo — `schema_version` de cada
  entrada pasa a ser el schema de la fuente detectado (mismo string para V1 que antes, nuevo
  string para V2); el `schema_version` **del manifiesto** no cambia (sigue
  `bybit-spot-trades-csv-gz-v1`) para no romper `load_manifest` ni los verificadores M9-A.
- **Capa Silver** (`silver.py`): parse tolerante a dos headers conocidos con salida única;
  entrada con `source_schema_version`. **Consumidores aguas abajo sin cambios**:
  `candles.py`/`gold.py`/`replay.py` leen solo claves específicas y validan el nivel de
  manifiesto (`SILVER_SCHEMA_VERSION`), por lo que una clave extra es compatible
  (`m9a1-09`/`m9a1-11` confirman `CANDLE_OUTPUTS=21` y manifests de candles/gold intactos).
- **Nuevo punto de entrada**: `schema_backfill_cli` (misma familia stdlib/`python3 -m` que los
  CLIs existentes, sin dependencias nuevas).
- **Fuera de git (lenovosrv):** `/srv/data/medallion` — 647 raw **byte-idénticos**
  (`BRONZE_RAW_HASHES_CHANGED=0`), 551 salidas Silver preexistentes **byte-idénticas**
  (`EXISTING_551_SILVER_HASHES_CHANGED=0`), manifest Bronze con 96 entradas corregidas
  (solo cambia `schema_version`), manifest Silver con 551 entradas + `source_schema_version`
  y 4 particiones nuevas (`2025-03-13/14/15` y `2025-06-16` → 555 en total), 0 `.part`,
  contenedores (paper-runner `b061332c3572` incluido) sin tocar.

## Índice del grafo

- [ ] Índice re-indexado tras el commit (`index_repository`) — **pendiente: exige commit autorizado**
- [ ] Cobertura verificada sobre archivos tocados (`check_index_coverage`) — pre-ejecución: 6/6
  rutas `no_recorded_issue` (generación 2026-09-28T06:01:58Z)

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| medallion (`test_source_schema` + `test_silver_trades` + `test_bronze_ingest` + `test_silver_candles` + `test_gold_dataset` + `test_trade_replay`) | **272 passed** | `m9a1-01b-unit-tests-medallion.log` |
| `tests --ignore=tests/integration` | **1227 passed, 1 skipped** | `m9a1-02b-unit-tests-full-count.log` |
| ruff check / ruff format --check / mypy src tests | **PASS / PASS / PASS (287 files, strict)** | `m9a1-03-lint-typing.log` |
| UAT lenovosrv (deploy → snapshot → FAIL CLOSED → backfill → transform 2025-03-13 → integridad → smoke → final) | **14/14 PASS** | `m9a1-04` … `m9a1-11` |
| Precommit local (scope/staged/check/secretos/ruff/mypy/pytest + condiciones desde evidencias) | **PASS** | `m9a1-12b-precommit-check.log` |
| Precommit remoto (re-hash raw+salidas, histograms, dev-range WF/holdout, cert/safeguard, paper) | **PASS** | `m9a1-13b-precommit-remote.log` |

## Cobertura

```
infrastructura/medallion  TOTAL   1726 stmts  64 miss  498 branch  56 BrPart  94%
bronze.py                 97%     silver.py   95%     schema_backfill_cli.py  94%
Required test coverage of 90% reached. Total coverage: 94.60%
```

## Calidad

```bash
uv run ruff check .            # All checks passed!
uv run ruff format --check .   # 328 files already formatted
uv run mypy src tests          # Success: no issues found in 287 source files
uv run pytest                  # 1227 passed, 1 skipped (tests --ignore=tests/integration)
```

## Seguridad

- [ ] Sin secretos en el diff (grep de `api_key|secret|password|token|PRIVATE` → 0)
- [ ] Sin archivos `.env` ni credenciales
- [ ] Backfill rechaza path traversal en `source_bronze_path` (`/` absoluto o `..`)
- [ ] Sin dependencias nuevas (stdlib puro) → **sin Dependency Proposal**
- [ ] Sin cambios en plataforma, red, contenedores ni certificación

## Riesgos y deuda

- **Deuda operativa (no de código):** 92 días V2 siguen sin transformar (M9-B); mientras
  tanto `SILVER=555/647`.
- El `schema_version` del manifiesto Bronze queda con un nombre que ya no describe el contenido
  (sigue `-v1`); documentado en D5 y en el docstring de `bronze.py` para no romper contratos.
- Si Bybit introduce una tercera variante de header, la descarga/backfill/transform fallan
  cerrados hasta adaptar el código + tests (comportamiento deseado).

## Mensaje propuesto

```
feat(medallion): M9-A1 Bybit Spot source schema evolution (V1/V2) + metadata backfill

- bronze.py: SOURCE_SCHEMA_V1/V2 + BRONZE_HEADER_V1/V2 + detect_source_schema/
  read_source_schema (header real por archivo; cualquier otro header u orden =>
  SourceSchemaError); download_day valida gzip + header y registra el schema
  detectado (limpia .part/directorio vacio si falla); backfill_source_schema
  corrige schema_version por entrada de forma deterministica/atomica verificando
  SHA-256 de cada raw (551 V1 / 96 V2), sin tocar .csv.gz
- silver.py: parse con ancho por schema (V1 5 col / V2 6 col) y salida canonica
  de 10 columnas identica para ambas; rpi no se propaga ni se reinterpreta;
  entrada con source_schema_version; transform FAIL CLOSED si el schema_version
  del manifest contradice al archivo detectado (fuerza backfill previo);
  backfill_source_schema completa el linaje de las 551 entradas existentes
  verificando source_bronze_sha256, sin reescribir salidas
- schema_backfill_cli.py: CLI stdlib --layer {all,bronze,silver} con
  --require-marker y salida BRONZE_V1_FILES/BRONZE_V2_FILES/SILVER_* (exit 0/1/2)
- tests: 43 casos TDD RED->GREEN en test_source_schema.py (deteccion, FAIL
  CLOSED, rpi no propagado con centinela, determinismo, backfill x2, manifiestos
  mal formados, CLI); 2 tests preexistentes adaptados a la validacion en descarga
- calidad: ruff check/format + mypy strict OK; suite 1227 passed, 1 skipped;
  capa medallion 94.60% (bronze 97%, silver 95%)
- UAT lenovosrv: FAIL CLOSED pre-backfill (exit=1, sin output parcial), backfill
  647/551 idempotente, transform SOLO 2025-03-13 (691556 filas 1:1, header
  canonico sin rpi, source_schema_version=v2) + smoke 3 fechas V2;
  BRONZE_RAW_HASHES_CHANGED=0, EXISTING_551_SILVER_HASHES_CHANGED=0,
  manifests candles/gold intactos, 0 .part, contenedores sin tocar,
  HEAD = dc5c0a2 sin commits nuevos
```

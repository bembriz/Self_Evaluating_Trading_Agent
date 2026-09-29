# M9-A — Full Development Dataset (Medallion)

**Estado:** ejecutado · **Rama:** `medalion` @ `4fd6b4c793bfde0f4719d9e6e54761e236a5fcaa`
**Fecha ejecución:** 2026-09-28/29 (UTC-06 / UTC) · **Host:** lenovosrv `192.168.100.24`
**Resultado:** `M9A_FULLDEV_FINAL_VALIDATION=PASS`

---

## 1. Alcance

Completar el dataset Medallion para el rango **único autorizado** `2023-09-09..2025-06-16`
(647 días consecutivos = `DEVELOPMENT_FIRST_DAY..DEVELOPMENT_LAST_DAY` de `splits/v1.json`):

1. Silver trades hasta 647 particiones.
2. Silver candles (7 timeframes) hasta 647 salidas por timeframe.
3. **Gold dataset nuevo** (no se tocó el Gold de 3 días).
4. Rerun de idempotencia sobre todo el rango.
5. Validación final + evidencias `m9a-*`.

**Restricciones respetadas:** sin `MARK-DONE` de M9, sin `git commit`, sin `git push`,
sin iniciar M9-B, sin leer walk-forward/holdout, sin tocar certificación ni paper-runner.

## 2. Rango y splits

| Campo | Valor |
|---|---|
| `DATE_FIRST` | 2023-09-09 |
| `DATE_LAST` | 2025-06-16 |
| `UNIQUE_DAYS` | 647 |
| `MISSING_DAYS` | 0 |
| `allowed_split` (Gold) | `DEVELOPMENT` |
| Fechas fuera de rango (todas las capas) | 0 |

## 3. Resultados por capa

| Capa | Antes | Ejecutado | Después | Hashes/manifest |
|---|---|---|---|---|
| Bronze `bybit/spot/ETHUSDT` | 647 (completo) | no re-descargó (`downloaded=0 skipped=647`) | 647 | raw `BRONZE_RAW_HASHES_CHANGED=0`; manifest `UNCHANGED` |
| Silver trades | 555 | `transformed=92 skipped=555 total=647` (702 s) | 647 | manifest `UNCHANGED`; 424 135 109 filas |
| Silver candles | 21 salidas | `transformed=4508 skipped=21 total=4529` (4467 s) | 4529 | manifest `UNCHANGED` |
| Gold replay datasets | 1 (3 días) | `created=1 skipped=0` (13 s) | 2 | dataset nuevo (ver §4) |

Tamaños finales: bronze 3,1 G · silver/trades 4,7 G · silver/candles 63 M · gold 1,4 M.

## 4. Dataset Gold nuevo (Full Development)

| Campo | Valor |
|---|---|
| `FULL_DEV_DATASET_ID` | `gold-replay-5ca68f44c37d2321f56a10ecbc08bc0584d70c17826f07604dbba77a8b71134a` |
| `FULL_DEV_MANIFEST_SHA256` | `c095d5740d9ca0c414ac0b11049008aa716262870edbeadc344dbb16188eb62e` |
| `manifest_version` | `gold-replay-dataset-v1` |
| Fechas | 647 (2023-09-09 → 2025-06-16), sin duplicados |
| `trades.partitions` | 647 (lista de rutas con sha256) |
| `candles.outputs` | 4529 (647 × 1m,5m,15m,30m,1h,4h,1d) |
| `ordering_fidelity` | `PARTIAL` · `source_order_preserved=true` |
| `lineage.verified` | `true` (`trade_partitions_referenced=647`, `candle_outputs_referenced=4529`) |
| Linaje de schema fuente | `bybit-spot-trades-csv-gz-v1=551`, `bybit-spot-trades-csv-gz-v2=96` |
| `replay-config.json` | `be8aae2df45670e1f987ab11e68f1471d0cb89104c0e53483d2d0de90fa18314` |

Gold de 3 días (UAT preexistente) **intacto**: `THREE_DAY_GOLD_UNTOUCHED=YES`
(`gold-replay-a8c49e0be9154194841a97c4f26225a76cef9fba8d9a6d080198359c124ebdc3`).

## 5. Idempotencia (rerun completo del rango)

| Etapa | Resultado | Evidencia |
|---|---|---|
| Bronze | `downloaded=0 skipped=647 total=647`, `DATA_CHANGED=0`, `MANIFEST_CHANGED=0` | `m9a-fulldev-05b-rerun1-poll.log` |
| Silver trades | `transformed=0 skipped=647 total=647`, `DATA_CHANGED=0`, `MANIFEST_CHANGED=0` | `m9a-fulldev-05b-rerun1-poll.log` |
| Silver candles | `transformed=0 skipped=4529 total=4529`, `DATA_CHANGED=0`, `MANIFEST_CHANGED=0` | `m9a-fulldev-06b-rerun2-poll.log` |
| Gold | `created=0 skipped=1`, mismo `dataset_id` y mismo `manifest_sha256`, `GOLD_CHANGED=0` | `m9a-fulldev-06b-rerun2-poll.log` |

## 6. Validación final (0 FAIL)

`python` de integridad + shell (evidencia `m9a-fulldev-07d-final-validation.log`):

- `DATE_CONTINUITY_{BRONZE,SILVER,CANDLES,GOLD}=PASS` (647/647/647/647, primeras/últimas fechas exactas).
- `CANDLE_OUTPUTS=4529`, `CANDLES_7_TF_EXACTOS=PASS` (647 por timeframe).
- `GOLD_INTEGRITY=PASS` (647 particiones, 4529 salidas, linaje `true`, fidelidad `PARTIAL`).
- `GOLD_ALLOWED_SPLIT_DEVELOPMENT=PASS`.
- `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0`, `NO_FECHAS_FUERA_DE_RANGO=0`.
- `PART_FILES_FINAL=0`, `GOLD_PART_FILES=0`.
- `BRONZE_RAW_HASHES_CHANGED=0`; manifests bronze/silver/candles sin cambios tras el rerun.
- `THREE_DAY_GOLD_UNTOUCHED=YES`; `SAFEGUARD_TOUCHED=NO`; `CERTIFICATION_TOUCHED_BY_M9A=NO`.
- `PAPER_CONTAINER_CHANGED=NO`; `CONTAINERS_SET_CHANGED=NO`.

## 7. Incidentes y atribución (transparencia)

1. **`set -e` abortó el script de Gold tras crear el dataset.** El script
   `fulldev-gold-run.sh` llevaba `set -e` desde la línea 26; el bloque de validación en
   Python salió con código 1 (2 aserciones mal formuladas: comparaba `trades.partitions`
   y `candles.outputs` como enteros cuando son **listas**) y el shell se detuvo sin escribir
   el marcador. El dataset **sí se creó correctamente**. Diagnóstico: `m9a-fulldev-04b/04c/04d`;
   verificación re-ejecutada en foreground con las claves correctas →
   `m9a-fulldev-04f-gold-verify.log` (`M9A_FULLDEV_GOLD=PASS`). En los scripts de rerun se
   sustituyó `set -e` por `set +e` (seguimiento manual con `fail`).
2. **`certification-state.json` cambió durante la ventana, pero no por M9-A.** El archivo
   (root-owned, montaje `/srv/docker/self-evaluating-trading-agent/certification`) lo
   reescribe el **job de reportes de 6 h del paper-runner** a las 10:01/16:01/22:01/04:01 UTC
   (último informe `paper-20260929-034500.md` → estado a las 04:01:22Z). M9-A ejecuta como
   `administrador` (uid 1000) sin `sudo` y ningún script suyo escribe en `/srv/docker`.
   Verificación: `m9a-fulldev-08-cert-atribucion.log` + checks `CERT_STATIC_FILES_UNCHANGED=YES`,
   `CERT_STATE_LIVE_FILE_ONLY=YES`, `CERT_IDENTITY_FROZEN_EQ_CURRENT=PASS`,
   `CERT_INVALIDATED_REASON=None`, `M9A_WRITES_OUTSIDE_SCOPE=NO`.
3. **Bug propio en `awk`** (comparaba `$2 != h[$2]`, nombre contra hash) hizo fallar la
   validación `07b/07c`; corregido a `$1 != h[$2]` → `07d` PASS.

## 8. Evidencias

| Evidencia | Contenido |
|---|---|
| `m9a-fulldev-01..01e-preflight.log` | preflight: HEAD/rama/origin `4fd6b4c`, 22 untracked permitidos, splits 647, deploy `git archive` verificado, capacidad, marker, baselines |
| `m9a-fulldev-02/02b/02c/02d-*` | Silver: lanzamientos, primer intento, poll PASS (`transformed=92`) |
| `m9a-fulldev-03/03b/03c/03d-*` | Candles: lanzamientos, polls, run PASS (`transformed=4508`) |
| `m9a-fulldev-04/04b/04c/04d/04e/04f-*` | Gold: lanzamiento, diagnósticos, tail-test, verificación PASS |
| `m9a-fulldev-05/05b-*` | Rerun bronze+silver PASS |
| `m9a-fulldev-06/06b-*` | Rerun candles+gold PASS |
| `m9a-fulldev-07/07b/07c/07d-*` | Validación final (07d = PASS definitivo) |
| `m9a-fulldev-08-cert-atribucion.log` | atribución del cambio de `certification-state.json` |

Artefactos remotos: `/srv/fast/medallion/m9a-logs/` (`fulldev-*-{run.sh,run.log,.out}`,
`*.sha256`, `fulldev-dataset-id.txt`, `fulldev-manifest.sha256`, `dates.txt`).

## 9. Siguiente paso

- `READY_FOR_M9A_COMMIT=YES` → presentar Commit Candidate y **esperar autorización**.
- `READY_FOR_M9B=YES` → **no iniciar** hasta gate aprobado.

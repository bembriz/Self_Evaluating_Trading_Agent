# Commit Candidate Report — 2026-09-28 (local) / 2026-09-29 (UTC)

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> **Candidate 012 — documental M9-A FULL DEVELOPMENT (sin código).**

## Objetivo

Cerrar documentalmente **M9-A FULL DEVELOPMENT**: registrar el dataset Medallion del
rango DEVELOPMENT completo (647 días) con su documentación de fase y **toda** la evidencia
generada (primer bulk → recovery → bloqueo por schema → resume Full DEVELOPMENT →
validación final + candidate prep). No contiene cambios de código: esos ya están
versionados en `4fd6b4c` (M9-A1).

## Rama

| Campo | Valor |
|---|---|
| branch | `medalion` |
| base commit | `4fd6b4c793bfde0f4719d9e6e54761e236a5fcaa` (HEAD == `origin/medalion`) |

## Archivos

- **Creados (57):**
  - `docs/phases/23/m9a-full-development-dataset.md` (documentación de fase)
  - `docs/phases/23/commit-candidate-012.md` (este reporte)
  - **55 logs** de evidencia `docs/phases/23/evidence/m9a-*.log`:
    - **22 preservados** del primer bulk/recovery/bloqueo por schema
      (`m9a-00..m9a-05c` = 14 + `m9a-recovery-01..07` = 8)
    - **28 del bloque Full DEVELOPMENT** (`m9a-fulldev-*`)
    - **5 de este candidate** (`m9a-cc012-*`: `state-validate`, `diff-check`, `secret-scan`,
      `final-staging`, `staged-final`)
- **Modificados (1):** `docs/phases/23/evidence/log.md` (índice de evidencias, +filas `m9a-*`)
- **Eliminados:** ninguno
- **Total staged: 58** (56 en `evidence/` = 55 logs + índice; 2 docs de fase)
- **Fuera de `docs/phases/23/`:** 0 · **CODE_FILES_CHANGED = 0**

## Diff

```bash
$ git diff --cached --name-only | grep -vc '^docs/phases/23/'
0                      # todo el diff es docs/phases/23
$ git diff --cached --name-only | grep -E '^(src/|tests/|deployment/)|progress\.yaml'
                       # sin resultados → 0 archivos de código, sin ledger
$ git diff --cached --numstat | awk '{a+=$1} END {print "files="NR" added="a}'
files=58 added=9505        # evidencia cruda verbatim + documentación; 0 borrados
```

> Snapshot exacto y conteos finales: evidencia `m9a-cc012-final-staging.log`.

## Arquitectura afectada

- **Ninguna.** `CODE_FILES_CHANGED=0`: solo `docs/**`. No se tocan `src/`, `tests/`,
  `deployment/`, `harness/` ni `harness/state/progress.yaml`.
- **Blast radius = 0** (sin símbolos ni módulos afectados; el diff no contiene código Python).
- Arquitectura hexagonal / contratos del producto: sin cambios.

## Índice del grafo

- [ ] Índice re-indexado tras el commit (`index_repository`) → *pendiente de APPROVED (§4.13)*
- [ ] Cobertura verificada sobre archivos tocados (`check_index_coverage`) → *pendiente*
- Estado actual del grafo: `status=ready`, 21004 nodos / 48206 aristas; fresco respecto de
  `4fd6b4c` (verificado en el arranque de esta sesión). Los `docs/**` no aportan nodos de código.

## Tests ejecutados

| Suite / verificación | Resultado | Evidencia |
|---|---|---|
| Estado final de dataset (solo lectura, sin reprocesar bulk) | **PASS** | `m9a-cc012-state-validate.log` |
| Validación final Full DEVELOPMENT (0 FAIL) | **PASS** | `m9a-fulldev-07d-final-validation.log` |
| Rerun idempotencia bronze+silver (0 changed) | **PASS** | `m9a-fulldev-05b-rerun1-poll.log` |
| Rerun idempotencia candles+gold (0 changed) | **PASS** | `m9a-fulldev-06b-rerun2-poll.log` |
| Verificación Gold (18 checks) | **PASS** | `m9a-fulldev-04f-gold-verify.log` |
| Atribución `certification-state.json` | **PASS** | `m9a-fulldev-08-cert-atribucion.log` |
| Suites unitarias / integración | **N/A** | 0 archivos de código en el diff |
| UAT de fase | pendiente (no forma parte de este candidate) | — |

## Cobertura

**N/A** — commit documental sin código; no altera cobertura de `src/` ni de `harness/`.

## Calidad

```bash
uv run ruff check .        # N/A (sin cambios de código)
uv run ruff format --check .
uv run mypy src tests      # N/A
uv run pytest              # N/A
$ git diff --cached --check
RC=2 → 168 avisos de "trailing whitespace" en 12 archivos:
        · 11 logs de evidencia cruda (salida verbatim de comandos)
        · 3 filas del índice evidence/log.md, generadas por harness/scripts/evidence.sh
        · 0 hallazgos en los artefactos escritos por el agente
          (m9a-full-development-dataset.md, commit-candidate-012.md) → RC=0
```

**Diff check (alcance y decisión):** los hallazgos están en logs capturados **verbatim**
(espacios finales que produce la propia salida del CLI) y en las filas del índice que
escribe `evidence.sh`. Se preservan **sin recortar** por requisito de evidencia auditable;
hay precedente en el repo: 38 archivos de `docs/` ya trackeados contienen la misma
característica (p. ej. `m0i-07-proxy-monitoring.log`, 15 líneas). Verificado de forma
separada: `git diff --cached --check -- m9a-full-development-dataset.md commit-candidate-012.md`
→ **RC=0**. → **DIFF_CHECK=PASS** con alcance documentado. Evidencias:
`m9a-cc012-diff-check.log` (ejecución original) y `m9a-cc012-staged-final.log` (repetición).

## Seguridad

- [x] Sin secretos en el diff
- [x] Sin archivos `.env` ni credenciales (ningún `.env`/`.pem`/`.key`/`id_rsa` staged)
- [x] Secret scanning limpio — 7 patrones, **HITS=0** en todos
  (clave privada, `AKIA…`, asignaciones `api_key/secret/password/token` con valor literal,
  `Bearer …`, URL con credenciales `user:pass@`, archivos sensibles, hex de 64 chars
  fuera de `*.log`)
- Únicos hex-64 en archivos no-log: 4 valores en la documentación que son **hashes
  SHA-256 públicos por diseño** (`dataset_id`, `manifest_sha256`, `replay-config.json`,
  id del Gold de 3 días) — no son credenciales.
- Evidencia: `m9a-cc012-secret-scan.log`.

## CERTIFICATION-STATE (declaración explícita)

`certification-state.json` **cambió durante la ventana de M9-A**, y ese cambio se atribuye a
la **ejecución periódica normal del paper-runner**, no a M9-A. **No se afirma que el archivo
permaneció byte-idéntico.**

| Verificación | Resultado | Evidencia |
|---|---|---|
| Cadencia del job 6-h del runner (informes 10:01/16:01/22:01/**04:01** UTC; `paper-20260929-034500.md` → estado a las **04:01:22Z**) | confirmada | `m9a-fulldev-08-cert-atribucion.log` |
| Paper container ID/StartedAt sin cambios (`PAPER_ID=b061332c3572…`, `STARTED=2026-09-19T04:00:04Z`, `STATUS=running`) | `PAPER_CONTAINER_CHANGED=NO` | `m9a-cc012-state-validate.log` |
| M9-A no escribió `certification-state` (ningún script M9-A escribe en `/srv/docker`; ejecución como uid 1000 sin `sudo`; archivo root-owned) | `M9A_WRITES_OUTSIDE_SCOPE=NO` | `m9a-cc012-state-validate.log` |
| certification/safeguard no reiniciados ni modificados (safeguard `mtime=2026-09-10`, `SAFEGUARD_TOUCHED=NO`) | PASS | `m9a-cc012-state-validate.log` |
| Único archivo distinto del baseline: `certification-state.json`; `PAPER_CERTIFICATION_REPORT.md` + 3 snapshots `*-INVALIDATED-*` idénticos | `CERT_STATIC_FILES_UNCHANGED=YES`, `CERT_STATE_LIVE_FILE_ONLY=YES` | `m9a-fulldev-07d-final-validation.log` |
| Identidad de certificación sin deriva (`frozen == current`, `INVALIDATED_REASON=None`, `STATUS=None`) | `CERT_IDENTITY_FROZEN_EQ_CURRENT=PASS`, `CERT_VALIDITY=PASS` | `m9a-fulldev-07d-final-validation.log` |
| Alcance | `CERTIFICATION_TOUCHED_BY_M9A=NO` | `m9a-fulldev-07d-final-validation.log` |

## Hechos principales registrados

1. **647 días DEVELOPMENT completos** (`2023-09-09..2025-06-16`), `UNIQUE_DAYS=647`,
   `MISSING_DAYS=0`, 0 fechas fuera de rango.
2. **Silver 647** particiones de trades (`transformed=92 skipped=555`; 424 135 109 filas).
3. **Candles 4529** salidas = **647 por cada uno de los 7 timeframes**
   (1m, 5m, 15m, 30m, 1h, 4h, 1d).
4. **Gold Full DEVELOPMENT creado** (el Gold de 3 días quedó intacto):
   - `FULL_DEV_DATASET_ID=gold-replay-5ca68f44c37d2321f56a10ecbc08bc0584d70c17826f07604dbba77a8b71134a`
   - `FULL_DEV_MANIFEST_SHA256=c095d5740d9ca0c414ac0b11049008aa716262870edbeadc344dbb16188eb62e`
   - `allowed_split=DEVELOPMENT`, `ordering_fidelity=PARTIAL`, `lineage.verified=true`
5. **Rerun completo idempotente: 0 changed** en las cuatro capas
   (`RERUN_BRONZE/SILVER/CANDLES/GOLD_CHANGED=0`; Gold `created=0 skipped=1` con mismo
   `dataset_id` y mismo hash).
6. **Schema V1/V2 = 551/96** en Silver y en el linaje del Gold.
7. **`WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0`**, `PART_FILES_FINAL=0`,
   `BRONZE_RAW_HASHES_CHANGED=0`.
8. **Paper/certificación no intervenidos** (`PAPER_CONTAINER_CHANGED=NO`,
   `CERTIFICATION_TOUCHED_BY_M9A=NO`, `SAFEGUARD_TOUCHED=NO`).

## Incidentes conocidos y su resolución

1. **`set -e` abortó el script de Gold tras crear el dataset** — el script llevaba `set -e`
   desde la línea 26 y el bloque de validación en Python salió con código 1 (2 aserciones
   mal formuladas: `trades.partitions`/`candles.outputs` son **listas**, no enteros), por lo
   que el shell se detuvo sin escribir el marcador. El dataset sí se creó correctamente.
   *Resolución:* diagnóstico (`m9a-fulldev-04b/04c/04d`), re-verificación en foreground con
   las claves correctas → `M9A_FULLDEV_GOLD=PASS` (`m9a-fulldev-04f`); `set -e` sustituido
   por `set +e` con seguimiento manual de `fail` en los scripts de rerun.
2. **`certification-state.json` cambió durante la ventana** — atribuido al job 6-h del
   paper-runner, no a M9-A. *Resolución:* ver §CERTIFICATION-STATE (evidencia
   `m9a-fulldev-08-cert-atribucion` + checks `07d`/`cc012`).
3. **Bug propio en `awk`** en la validación del candidate: se comparaba `$2 != h[$2]`
   (nombre vs hash) en lugar de `$1 != h[$2]`, lo que marcó los 5 archivos de certificación
   como cambiados. *Resolución:* corregido; re-ejecución → solo
   `certification-state.json` difiere (`m9a-cc012-state-validate.log`).

## Riesgos

- Evidencia cruda con espacios finales: preservada deliberadamente (auditable > estética);
  si en el futuro se exige `--check` limpio, debe resolverse con `.gitattributes` y no
  editando los logs.
- El estado vivo de certificación seguirá evolucionando con el runner: cualquier comparación
  futura debe usar el enfoque "archivos estáticos idénticos + sólo `certification-state.json`
  vivo", no igualdad byte a byte.

## Deuda técnica

- Validar manifiestos con aserciones tipadas (`len(...)`) en los scripts de verificación
  (los scripts viven en `/tmp` del host, no en el repo).
- Los scripts de orquestación M9-A (launch/poll/rerun) no están versionados; si se reutilizan
  en M9-B, subirlos a `harness/` con su propio commit.

## Mensaje de commit propuesto

```
docs(medallion): record M9-A full DEVELOPMENT dataset

- 647 días DEVELOPMENT (2023-09-09..2025-06-16) completos: 0 missing, 0 fuera de rango
- Silver trades 647 particiones (92 nuevas en este bloque) y candles 4529 salidas (647 x 7 TF)
- Gold Full DEVELOPMENT creado: dataset_id=gold-replay-5ca68f44c37d2321f56a10ecbc08bc0584d70c17826f07604dbba77a8b71134a
  manifest_sha256=c095d5740d9ca0c414ac0b11049008aa716262870edbeadc344dbb16188eb62e
- rerun idempotente completo: bronze/silver/candles/gold 0 changed
- linaje de schema fuente V1=551 / V2=96 (fidelidad PARTIAL, source_order_preserved)
- walk-forward y holdout reads = 0; paper-runner y certificación no intervenidos
- incorpora las 22 evidencias M9-A/recovery preservadas + 29 del bloque Full DEVELOPMENT
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

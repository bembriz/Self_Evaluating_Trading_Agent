# Commit Candidate Report — 2026-09-27

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

Registrar M4 (Silver Canonical Trades): transformación determinista Bronze → Silver de
los 3 días DEVELOPMENT en lenovosrv (schema canónico de 10 columnas, Decimal sin float,
sin dedupe, orden total documentado `ORDERING_FIDELITY=PARTIAL` +
`source_order_preserved` por partición, linaje por fila, manifest por partición), con 28
unit tests, UAT RUN1/RUN2/negative en el servidor, corrección de fidelidad
(`m4-10`…`m4-12`: manifest `FULL→PARTIAL` sin tocar los CSV) y la marca
`23/m4-silver-trades` = done en el ledger.

## Rama

| Campo | Valor |
|---|---|
| branch | `medalion` |
| base commit | `cc6d75f22588ffeee0a058ae8e449ac409d890cb` (= `origin/medalion`) |

## Archivos

- **Creados (13):**
  - `src/infrastructure/medallion/silver.py` — `transform_day/transform_days`: split guard
    pre-creación de destino → hash Bronze vs manifest → validación total de filas (FAIL
    CLOSED sin output parcial) → orden `(event_timestamp, source_row_number)` → gzip
    determinista `.part` (mtime=0, sin FNAME, LF, UTF-8) → round-trip → manifest atómico
    → `os.replace` → ops log separado
  - `src/infrastructure/medallion/silver_cli.py` — CLI stdlib (`--bronze-dir --dest-dir
    --symbol --dates --require-marker`), exit 0/1/2
  - `tests/test_silver_trades.py` — 28 unit tests sin red
  - `docs/phases/23/m4-silver-trades.md` — doc de milestone
  - `docs/phases/23/evidence/m4-*` — 13 evidencias (intento fallido m4-02 documentado:
    mkdir pre-guard corregido; `m4-09` = precommit verify; `m4-10`…`m4-12` = corrección
    de fidelidad: calidad local, regeneración de manifest/output en servidor, RUN2)
- **Modificados (2):** `docs/phases/23/evidence/log.md`, `harness/state/progress.yaml`
  (`23/m4-silver-trades` → `done` vía `progress.py mark-done`)
- **Eliminados:** ninguno

## Diff

```bash
$ git diff --cached --shortstat
20 files changed, 1468 insertions(+), 2 deletions(-)
$ git diff --cached --check
rc=0   # 0 hallazgos
```

## Arquitectura afectada

- Amplía `infrastructure.medallion` con la capa Silver (ADR-0005/0007,
  `docs/design/medallion-replay-architecture.md` §Silver). `bronze.py`, `cli.py`,
  `split_guard.py` y la capa Bronze **no se modifican**; consumidor futuro = M5 (candles).
- lenovosrv (fuera de git): creadas 3 particiones Silver + manifest + ops en
  `/srv/data/medallion/silver/trades/ETHUSDT/`; Bronze intacto; contenedores
  productivos intactos (IDs/StartedAt = baseline).
- Sin dependencias nuevas (stdlib: `csv`, `gzip`, `io`, `decimal` vía regex/validación).

## Índice del grafo

- [ ] Índice re-indexado tras el commit (`index_repository`) — pendiente post-commit
- [ ] Cobertura verificada sobre archivos tocados (`check_index_coverage`) — pendiente
      post-commit (`docs/` y `harness/state` excluidos por diseño)

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| `pytest tests/test_silver_trades.py tests/test_bronze_ingest.py --cov=infrastructure.medallion` | PASS — cobertura 92.32% (silver 91%) | `m4-02b-unit-tests.log` |
| `ruff check .` + `ruff format --check .` + `mypy src tests` + `pytest tests --ignore=tests/integration` | PASS — **1013 passed, 1 skipped** | `m4-03-repo-quality.log` |
| Análisis de fuente (schema/orden/duplicados, 3 días) | PASS | `m4-01-bronze-analysis.log` |
| UAT RUN1 lenovosrv | PASS — `transformed=3`, SOURCE_ROWS=SILVER_ROWS=1 880 793 | `m4-06-uat-run1.log` |
| UAT RUN2 idempotencia | PASS — `skipped=3`, 0 changed (hashes+manifest idénticos) | `m4-07-uat-run2.log` |
| UAT negative (WF/holdout/pre-DEV/fecha/marker) | PASS — exit 1/2/1, `WF_READS=0 HOLDOUT_READS=0` | `m4-08-uat-negative.log` |
| Corrección: calidad local | PASS — ruff+format+mypy, 58 tests (92.42%), suite **1013 passed, 1 skipped** | `m4-10-correction-quality.log` |
| Corrección: regeneración manifest | PASS — `FULL→PARTIAL`+`source_order_preserved`; outputs byte-idénticos al RUN1 (`OUTPUT_DATA_HASH_CHANGED=NO`) | `m4-11-manifest-regeneration.log` |
| Corrección: RUN2 revalidación | PASS — `skipped=3`, 0 changed, linaje PASS, `WF_READS_DELTA=0` | `m4-12-run2-revalidation.log` |

## Cobertura

- Módulos Silver: `silver.py` **91%**, `silver_cli.py` **90%**; total capa medallion
  **92.32%** con `--cov=infrastructure.medallion --cov-branch --cov-fail-under=90` → PASS
- Suite completa producto: **1013 passed, 1 skipped** (PG local caído = preexistente)

## Calidad

```bash
uv run ruff check .                 # All checks passed!
uv run ruff format --check .        # all files formatted
uv run mypy src tests               # Success: no issues found in 273 source files
uv run pytest tests --ignore=tests/integration
                                    # 1013 passed, 1 skipped
```

## Seguridad

- [x] Sin secretos en el diff (grep `password|api_key|secret|token|BEGIN … PRIVATE` → 0 hits)
- [x] Sin archivos `.env` ni credenciales; evidencia m4 sin sudo ni credenciales
- [x] Preexistente y NO de este commit: credencial sudo histórica ya versionada en logs
  de fase 16 → "Credencial sudo histórica detectada en evidencia ya versionada. Rotación
  requerida y limpieza de historial pendiente en gate separado."
  (`SECURITY_CREDENTIAL_ROTATION_REQUIRED=YES`, `GIT_HISTORY_CLEANUP_REQUIRED=YES`)

## Riesgos

- Bajo: código nuevo aislado (`silver.py`/`silver_cli.py`), solo consumido por su CLI y
  sus tests; Bronze intocado (solo lectura + hash check).
- `ORDERING_FIDELITY=PARTIAL` (corregido): el archivo Spot no trae
  `native_sequence`/cross-sequence ⇒ con timestamps repetidos no es demostrable el orden
  del matching engine. `source_order_preserved` se calcula por partición (los 3 días
  reales: `true`, 0 inversiones ts en `m4-01`). Si M5-M8 lo reutilizan sobre otros días,
  el flag se recalcula automáticamente.
- Validación de filas con regex estricta (decimal canónico sin exponente): si una fuente
  futura trajera notación exponencial, fallaría FAIL CLOSED por diseño (no silencioso).

## Deuda técnica

- `coverage.json` global de repo no re-ejecutado en M4 (umbral del gate de fase al cierre).
- M5 (Silver candles) consumirá este layer; `ordering_fidelity`/`source_order_preserved`
  se recalculan por partición en cada transform.
- Rotación de credencial + limpieza de historial → gate separado (preexistente).

## Mensaje de commit propuesto

```
feat(medallion): M4 canonical deterministic Silver trades

- silver.py: Bronze -> Silver deterministico (gzip mtime=0, manifest atomico,
  .part + rename); Decimal-validacion sin float; sin dedupe; FAIL CLOSED en
  fila invalida o hash Bronze != manifest; linaje por fila (source_file/sha/row)
- orden total (event_timestamp, source_row_number); ORDERING_FIDELITY=PARTIAL
  + source_order_preserved por particion (sin native_sequence en la fuente;
  los 3 dias reales preservan orden: 0 inversiones ts)
- silver_cli.py: CLI stdlib para lenovosrv (exit 0/1/2)
- tests: 28 unit tests; capa medallion 92.32%; suite 1013 passed
- UAT lenovosrv: RUN1 transformed=3 (1880793 filas == Bronze), RUN2 skipped=3
  (0 changed); correccion manifest FULL->PARTIAL con outputs byte-identicos;
  WF/holdout rechazados (WF_READS=0, FINAL_HOLDOUT_READS=0)
- ledger: 23/m4-silver-trades -> done (via progress.py mark-done)
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

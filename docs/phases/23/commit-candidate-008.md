# Commit Candidate Report — 2026-09-28

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

Registrar M6 (Gold Replay Dataset): manifest Gold inmutable y reproducible que
**referencia** (sin copiar) las 3 particiones Silver trades + los 21 outputs de
candles de 2024-06-01/02/03, con `dataset_id` content-addressed, validación FAIL
CLOSED de hashes + linaje candles→trades antes de crear nada, `replay-config.json`
fijo (15m decisión / contexto 1h,4h / `TRADE_SEQUENCE_TAKER_PROXY` / velas
confirmadas / limitaciones explícitas, sin parámetros de estrategia ni riesgo), y la
marca `23/m6-gold` = done en el ledger.

## Rama

| Campo | Valor |
|---|---|
| branch | `medalion` |
| base commit | `37cd798a64f359ebde49cb2decce6689666746be` (= `origin/medalion`) |

## Archivos

- **Creados (14):**
  - `src/infrastructure/medallion/gold.py` — `create_dataset`: split guard →
    validación de manifests/hashes/linaje → identity canónico → `dataset_id` →
    `.part` + round-trip + rename; SKIP idéntico / FAIL CLOSED distinto
    (`GoldError`, `InputHashMismatchError`, `LineageMismatchError`,
    `DatasetConflictError`)
  - `src/infrastructure/medallion/gold_cli.py` — CLI stdlib (exit 0/1/2)
  - `tests/test_gold_dataset.py` — 40 unit tests (TDD RED→GREEN)
  - `docs/phases/23/m6-gold-replay-dataset.md` — doc de milestone
  - `docs/phases/23/evidence/m6-*` — 9 evidencias (unit/quality/preflight[×2:
    intento con bug registrado]/deploy/RUN1/RUN2+det/verificación/negatives)
  - `docs/phases/23/commit-candidate-008.md` — este reporte
- **Modificados (2):** `docs/phases/23/evidence/log.md`, `harness/state/progress.yaml`
  (`23/m6-gold` → `done` vía `progress.py mark-done`)
- **Eliminados:** ninguno

## Diff

```bash
$ git diff --cached --shortstat
16 files changed, 1772 insertions(+), 2 deletions(-)
$ git diff --cached --check
rc=0   # 0 hallazgos
```

## Arquitectura afectada

- Amplía `infrastructure.medallion` con la capa Gold (ADR-0005/0007,
  `docs/design/medallion-replay-architecture.md` §7). `bronze.py`, `silver.py`,
  `candles.py`, `split_guard.py` **no se modifican**; consumidor futuro = M7 (replay
  de dos relojes) + M8.
- lenovosrv (fuera de git): creados `/srv/data/medallion/gold/replay-datasets/ETHUSDT/
  gold-replay-a8c49e0b…/` (manifest.json + replay-config.json) + `ops-gold.jsonl`;
  Silver trades/candles y Bronze verificados intactos tras UAT.
- Sin dependencias nuevas (stdlib: `json`, `hashlib`, `shutil`, `os`).

## Índice del grafo

- [ ] Índice re-indexado tras el commit (`index_repository`) — pendiente post-commit
- [ ] Cobertura verificada sobre archivos tocados (`check_index_coverage`) — pendiente
      post-commit (`docs/` y `harness/state` excluidos por diseño)

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| `pytest <5 archivos medallion> --cov=infrastructure.medallion --cov-branch --cov-fail-under=90` + ruff + mypy | PASS — **163 tests**, cobertura **96.11%** (gold.py **100%**, gold_cli 96%) | `m6-01-unit-tests.log` |
| `ruff check .` + `ruff format --check .` + `mypy src tests` + `pytest tests --ignore=tests/integration` | PASS — **1107 passed, 1 skipped** | `m6-02-repo-quality.log` |
| Preflight lenovosrv (HEAD + marker + 3/21 + PARTIAL + dest ausente) | PASS | `m6-03-preflight-ok.log` |
| UAT RUN1 | PASS — `created=1`, 2 archivos, 0 `.part` | `m6-05-uat-run1.log` |
| UAT RUN2 + determinismo (destino fresco) | PASS — `skipped=1`, `RUN2_CHANGED=0`, mismo id + bytes idénticos | `m6-06-uat-run2-determinism.log` |
| Verificación independiente (3+21 hashes, linaje, id recomputado, Silver/Bronze intactos) | PASS | `m6-07-uat-verify.log` |
| Negatives (guard WF/holdout pre-lectura, hash/linaje/partición FAIL CLOSED, canónico intacto) | PASS — `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0` | `m6-08-uat-negative.log` |

## Cobertura

- `gold.py` **100%** statements/branch; `gold_cli.py` 96%; capa medallion
  **96.11%** con `--cov=infrastructure.medallion --cov-branch --cov-fail-under=90` → PASS
- Suite completa producto: **1107 passed, 1 skipped** (PG local caído = preexistente)

## Calidad

```bash
uv run ruff check .                 # All checks passed!
uv run ruff format --check .        # 323 files already formatted
uv run mypy src tests               # Success: no issues found in 282 source files
uv run pytest tests --ignore=tests/integration
                                    # 1107 passed, 1 skipped
```

## Seguridad

- [x] Sin secretos en el diff (grep `password|api_key|secret|token|BEGIN … PRIVATE` → 0 hits)
- [x] Sin archivos `.env` ni credenciales; evidencia m6 sin sudo ni credenciales
- [x] Preexistente y NO de este commit: credencial sudo histórica ya versionada en logs
  de fase 16 → "Credencial sudo histórica detectada en evidencia ya versionada. Rotación
  requerida y limpieza de historial pendiente en gate separado."
  (`SECURITY_CREDENTIAL_ROTATION_REQUIRED=YES`, `GIT_HISTORY_CLEANUP_REQUIRED=YES`)

## Riesgos

- Bajo: código nuevo aislado (`gold.py`/`gold_cli.py`), solo lectura de Silver +
  escritura de 2 archivos pequeños; Silver/Bronze intocados (verificado por hashes).
- El `dataset_id` incluye el `replay_config` completo: cambiar la config futura de
  replay ⇒ nuevo id y nuevo dataset (por diseño, regla §4.9).
- `source_roots` en el manifest documenta layout relativo; un layout distinto no
  altera el id (los roots no entran al identity) pero sí la verificación externa.

## Deuda técnica

- `coverage.json` global de repo no re-ejecutado en M6 (umbral del gate de fase).
- M7 consumirá el manifest Gold directamente; si el replay necesita campos extra
  (p. ej. hashes Bronze por partición ya referenciados en Silver), ampliar identity
  ⇒ nuevo `dataset_id` y nuevo experimento.
- Campos adicionales de `docs/design/… §7` (`fee_model_version`,
  `slippage_model_version`, `created_by_version`) se añadan cuando esas versiones
  existan en código (hoy viven en replay-config/separados).

## Mensaje de commit propuesto

```
feat(medallion): M6 immutable Gold replay dataset manifest

- gold.py: create_dataset valida (FAIL CLOSED) manifests Silver, hash de las
  3 particiones trades + 21 candle outputs y linaje candles -> trades antes
  de crear nada; split guard DEVELOPMENT antes de leer (WF/holdout reads=0)
- dataset_id content-addressed: sha256 del canonical identity (symbol, dates,
  schemas, fidelity, partitions, outputs, replay_config) sin wall-clock;
  mismo contenido => mismo id; id con contenido distinto => FAIL CLOSED
- manifest.json (gold-replay-dataset-v1): 3+21 refs con hashes, row/candle
  counts, ordering_fidelity=PARTIAL, source_order_preserved, lineage
  verificable, candle_count_by_timeframe, sha de replay-config
- replay-config.json (replay-config-v1): decision 15m, contexto 1h/4h,
  execution_model TRADE_SEQUENCE_TAKER_PROXY, velas confirmadas solo,
  fill = primer trade elegible desde la decision, limitaciones (sin bid/ask,
  depth, queue, impacto, latencia), sin params de estrategia/riesgo
- atomicidad .part + round-trip + rename; ops-gold.jsonl separado (unico
  lugar con timestamps); SKIP si identico
- gold_cli.py: CLI stdlib (exit 0/1/2); tests: 40 casos, gold.py 100% branch,
  capa medallion 96.11%; suite 1107 passed
- UAT lenovosrv: RUN1 created=1 (dataset gold-replay-a8c49e0b...), RUN2
  skipped=1 RUN2_CHANGED=0, destino fresco mismo id/bytes; verificacion
  independiente 3+21 hashes + linaje + id recomputado PASS; Silver/Bronze
  intactos; negatives FAIL CLOSED
- ledger: 23/m6-gold -> done (via progress.py mark-done)
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

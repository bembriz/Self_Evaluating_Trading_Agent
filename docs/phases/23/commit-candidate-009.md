# Commit Candidate Report — 2026-09-28

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

Registrar M7 (Trade-Level Replay Engine): motor de replay trade-a-trade de dos relojes
(delas confirmadas → decisiones; trades → fills/riesgo) sobre el dataset Gold
`gold-replay-a8c49e0b…`, con validación FAIL CLOSED completa del dataset antes de leer
Silver, decisiones guionizadas de validación, contabilidad exacta (gross − slippage − fees,
fees + slippage incluidos), ledger JSONL determinista idempotente (`.part` + round-trip +
rename; sin wall-clock), CLI stdlib, 77 unit tests TDD, UAT en lenovosrv con re-walk
independiente + 6 negativos FAIL CLOSED, y la marca `23/m7-trade-replay` = done en el ledger.

## Rama

| Campo | Valor |
|---|---|
| branch | `medalion` |
| base commit | `04441adc114041a4984f37e630c2c3b3dde0c408` (= `origin/medalion`) |

## Archivos

- **Creados (14):**
  - `src/infrastructure/medallion/replay.py` — motor `_Engine` (dos relojes, orden
    fill→drain→risk, sweep final), `validate_dataset` (orden completo FAIL CLOSED incl.
    split guard antes de leer), `load_candles`, `iter_trades`, `ledger_payload`
    (run_meta 21 claves + registros con 27 campos requeridos), `write_ledger`
    (created/skipped/`LedgerConflictError`), `ScriptedScheduleProvider`,
    `ReplayError`/`DatasetValidationError`/`LedgerConflictError`
  - `src/infrastructure/medallion/replay_cli.py` — CLI stdlib (`STATUS=`/`SUMMARY=`,
    exit 0/1/2)
  - `tests/test_trade_replay.py` — 77 unit tests (TDD RED→GREEN)
  - `docs/phases/23/m7-trade-replay.md` — doc de milestone
  - `docs/phases/23/evidence/m7-*` — 10 evidencias (unit/quality/preflight/
    deploy×3: 2 intentos fallidos registrados/RUN1/RUN2+det×2/verificación)
  - `docs/phases/23/commit-candidate-009.md` — este reporte
- **Modificados (2):** `docs/phases/23/evidence/log.md`, `harness/state/progress.yaml`
  (`23/m7-trade-replay` → `done` vía `progress.py mark-done`)
- **Eliminados:** ninguno

## Diff

```bash
$ git diff --cached --shortstat
17 files changed, 3388 insertions(+), 2 deletions(-)
$ git diff --cached --check
rc=0   # 0 hallazgos
```

## Arquitectura afectada

- Amplía `infrastructure.medallion` con el motor de replay (ADR-0005,
  `docs/design/medallion-replay-architecture.md` §8–§11). Reutiliza sin modificar
  `domain.market.indicators.atr`, `domain.market.candle.Candle`,
  `domain.risk.stops`/`RiskConfig`, `split_guard.ensure_development_day` y el dataset
  Gold de M6. Consumidor futuro: M8 (estrategias reales sobre el mismo motor).
- lenovosrv (fuera de git): creado `/srv/fast/medallion/replay-work/ledger.jsonl`
  (24 líneas, sha `6d64b62b…`); copia de trabajo en `/tmp/m7/src`; Silver/Bronze/Gold
  re-verificados intactos por hashes tras el UAT; paper-runner sin cambios.
- Sin dependencias nuevas (stdlib: `bisect`, `csv`, `gzip`, `json`, `argparse`…).

## Índice del grafo

- [ ] Índice re-indexado tras el commit (`index_repository`) — pendiente post-commit
- [ ] Cobertura verificada sobre archivos tocados (`check_index_coverage`) — pendiente
      post-commit (`docs/` y `harness/state` excluidos por diseño)

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| `pytest <6 archivos medallion> --cov=infrastructure.medallion --cov-branch --cov-fail-under=90` + ruff + mypy | PASS — **240 tests**, cobertura **94.01%** (replay.py **91%**, replay_cli 96%) | `m7-01-unit-tests.log` |
| `ruff check .` + `ruff format --check .` + `mypy src tests` + `pytest tests --ignore=tests/integration` | PASS — **1184 passed, 1 skipped** | `m7-02-repo-quality.log` |
| Preflight lenovosrv (Gold/Silver hashes, paper baseline, replay-work limpio) | PASS | `m7-03-preflight.log` |
| Deploy copy a `/tmp/m7/src` (2 intentos fallidos registrados + OK) | PASS — `IMPORT_OK`, 27 campos, escenario/riesgo | `m7-04c-deploy-copy.log` |
| UAT RUN1 | PASS — `STATUS=created`, `45/23/22/0/23`, `trades=1880793`, motivos 16/2/5, 10 s | `m7-05-uat-run1.log` |
| UAT RUN2 + determinismo (intento con diff de rutas registrado + OK) | PASS — `RUN2_LEDGER_IDENTICAL=YES`, re-run `skipped=1` | `m7-06b-uat-run2-determinism.log` |
| Verificación independiente + negatives | PASS — re-walk sin motor (fills/riesgo/contabilidad/velas), N1–N6 FAIL CLOSED, `PAPER_CONTAINER_CHANGED=NO`, `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0` | `m7-07-uat-verify.log` |

## Cobertura

- `replay.py` **91%** statements/branch; `replay_cli.py` 96%; capa medallion
  **94.01%** con `--cov=infrastructure.medallion --cov-branch --cov-fail-under=90` → PASS
- Suite completa producto: **1184 passed, 1 skipped** (PG local caído = preexistente)

## Calidad

```bash
uv run ruff check .                 # All checks passed!
uv run ruff format --check .        # 326 files already formatted
uv run mypy src tests               # Success: no issues found in 285 source files
uv run pytest tests --ignore=tests/integration
                                    # 1184 passed, 1 skipped
```

## Seguridad

- [x] Sin secretos en el diff (grep `password|api_key|secret|token|BEGIN … PRIVATE` →
  1 match, es la línea auto-referencial de este propio reporte que documenta el patrón;
  0 hits en código/evidencia)
- [x] Sin archivos `.env` ni credenciales; evidencia m7 sin sudo ni credenciales
- [x] Preexistente y NO de este commit: credencial sudo histórica ya versionada en logs
  de fase 16 → "Credencial sudo histórica detectada en evidencia ya versionada. Rotación
  requerida y limpieza de historial pendiente en gate separado."
  (`SECURITY_CREDENTIAL_ROTATION_REQUIRED=YES`, `GIT_HISTORY_CLEANUP_REQUIRED=YES`)

## Riesgos

- Bajo: código nuevo aislado (`replay.py`/`replay_cli.py`), solo lectura de Silver/Gold +
  escritura de 1 ledger fuera de git; Silver/Bronze/Gold intocados (verificado por hashes).
- La estrategia guionizada es **solo** para validar contratos: M8 la sustituye por las
  estrategias reales (mismo motor, otro `DecisionProvider`) ⇒ nueva corrida/ledger, no
  silenciar prompts/modelos.
- Semántica `PARTIAL`: orden de trades por día garantizado monotónico (re-walk lo confirma);
  igualdad de timestamps resuelta por orden de archivo (documentado en ADR-0005).
- `max_time_in_position` está en el catálogo pero no se implementa en M7 (límite de scope
  del gate); añadirlo ⇒ decisión nueva + nuevos experimentos.

## Deuda técnica

- `coverage.json` global de repo no re-ejecutado en M7 (umbral del gate de fase).
- Contexto 1h/4h se carga y expone en `ContextSnapshot` pero el proveedor guionizado lo
  ignora; M8 lo consumirá (hoy sin asserts de contexto).
- Cobertura de `replay.py` 91% (faltan ramas de error poco comunes: round-trip caído,
  headers de candles corruptos, etc.); aceptable para el gate (≥90%, críticos cubiertos
  por re-walk + negatives).

## Mensaje de commit propuesto

```
feat(medallion): M7 two-clock trade-level replay engine

- replay.py: motor determinista dos relojes (velas 15m confirmadas ->
  decisiones; trades Silver -> fills/riesgo) con orden fill pendiente ->
  drenaje FIFO -> risk eval, sweep final de unfilled/edge/end_of_dataset
- validacion FAIL CLOSED completa del Gold antes de leer Silver (split
  guard DEVELOPMENT antes de tocar nada, config sha, estructura,
  source_roots, linaje, identidad recompute==manifest==dirname, hashes
  de 3+21 entradas); InputHashMismatchError/DatasetValidationError/
  LedgerConflictError
- exits: stop_loss/trailing_stop/take_profit/strategy_exit/
  end_of_dataset con clasificacion exacta por exit_reference vs
  entry_execution; MFE/MAE identidad exacta; contabilidad
  net = gross - slippage - fees con fees+slippage incluidos
- ledger JSONL determinista: run_meta 21 claves + registros (27 campos
  requeridos), sin wall-clock, .part + round-trip + rename, created/
  skipped/conflict idempotente
- replay_cli.py: CLI stdlib STATUS/SUMMARY (exit 0/1/2); tests: 77
  casos TDD RED->GREEN, replay.py 91% branch, capa medallion 94.01%;
  suite 1184 passed
- UAT lenovosrv: RUN1 created=1 sobre gold-replay-a8c49e0b...
  (45/23/22/0/23, trades=1880793, motivos 16/2/5, 10s); RUN2 byte-
  identico (RUN2_LEDGER_IDENTICAL=YES, sha 6d64b62b...) y re-run
  skipped=1; re-walk independiente (fills primer elegible, trigger ==
  close de vela, contabilidad exacta, stream 1880793 monotono) PASS;
  negatives FAIL CLOSED (split pre-lectura, config/identidad/hash,
  ledger conflict, usage); Gold/Silver/ledger intactos,
  PAPER_CONTAINER_CHANGED=NO, WALK_FORWARD_READS=0,
  FINAL_HOLDOUT_READS=0
- ledger: 23/m7-trade-replay -> done (via progress.py mark-done)
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

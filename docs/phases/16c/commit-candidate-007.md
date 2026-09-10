# Commit Candidate Report — 2026-09-09 · Fase 16c.6 · Cierre 0.2.0 (Commit Candidate FINAL)

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> Estado del entregable: **READY_FOR_USER_GATE** — sin commit/push/merge/tag/redeploy/
> Paper Certification hasta APPROVED explícito del usuario.
> **Re-ejecutado contra el árbol FINAL post-Task 8d** (2026-09-09 noche): incluye F1, F2 y la
> corrección final del punto 1 (preservación del `frozen` anclado) + 4 tests de regresión.
> Cifras y blast radius refrescados; sustituyen a las pasadas pre-F1/F2 y pre-8d.

## Objetivo

Cerrar la **Fase 16c** (Paper Certification restart-safe / schema v2) entregando el ciclo
completo **productor real → estado v2 (crash-safe) → evaluador determinista**, y anclar el
producto a **0.2.0**:

- Productor real en `src/` que escribe `certification-state` con **schema v2**
  (`frozen` 10 campos congelados + `operational` con 11 campos y conteos), con **escritura
  crash-safe** (fsync + atomic replace), **reloj explícito NOT_STARTED→START**,
  **reconciliación contable** del engine (bit-exacta, componente a componente) y
  **anti-corrupción compensada** (fail-closed, sin PASO si el libro previo no cierra).
- **F1 (whole-branch review)**: `start_certification` escribe directamente un envelope
  `schema_version: 2` **completo** al anclar (session_id, session_started_at, frozen con anchor,
  current espejo, operational presente, accounting_book) — sin depender de heurística
  `{frozen,current}⇒v2`; corrige el deploy fresco donde la escritura periódica reclasificaba
  el ancla como legacy y el reloj v2 no progresaba. Regresión: `fresh start → periodic write
  → operational v2 RUNNING` (incl. `state_continuity == PASS`).
- **F2 (whole-branch review)**: reconciliación **three-way** con checkpoint/cursor
  (`live == full == incremental`, componente a componente: cash/position_qty/avg_entry/
  realized_pnl/fees/equity), `BookState` con `entry_fees` + `last_event_ms`; el checkpoint
  avanza **solo en PASS** y conserva el previo en FAIL; detecta corrupción/borrado de eventos
  viejos (full≠incremental) y de eventos nuevos (reconstruida≠live), incluida corrupción
  compensada.
- **Task 8d — punto 1 (preservación del ancla)**: `_resolve_frozen` conserva el `frozen`
  anclado/RUNNING **byte a byte aunque la identidad (symbol/timeframe/versión) difiera**; el
  mismatch se reporta como `frozen_versions` FAIL **sin re-anclar** y sin perder el reloj.
  `start_certification` nunca re-ancla un RUNNING (el guard fail-closed de conflicto de sesión
  sigue intacto); +4 tests de regresión (symbol mismatch, timeframe mismatch, START sobre
  RUNNING con contexto distinto rechazado sin re-ancla, identidad pristina completa).
- **E2E integrado productor→estado→evaluador** (**9 tests**, casos E2E-1..10 + caso 9
  `_mid_run_fill_events`) que da PASS: el estado v2 emitido por el runner alimenta
  `evaluate_certification` y supera los criterios operacionales (incluye strict JSON lossless
  y recovery/auditabilidad).
- **Safeguard drills** en el arnés por secuencias canónicas (kill_switch 6 pasos,
  daily_loss 5 pasos) con matcher fail-closed.
- **Bump a 0.2.0** (`src/version.py` + `pyproject.toml`) con test anti-drift
  (`tests/test_version_consistency.py`). El ancla 0.2.0 invalida cualquier certificación
  0.1.x previa por diseño; **Paper NO queda marcado como certificado** en este commit.
- Gates de calidad y evidencia auditable en `docs/phases/16c/evidence/`.

## Rama

| Campo | Valor |
|---|---|
| branch | `fix/phase-16c-restart-safe` |
| base commit | `66448dc` (`feat(phase-16c): paper certification operational gate`) |

## Archivos

Cambio total vs base (staged final, `git diff --cached --stat`): **35 archivos**, **+8218 / −18**
(este reporte y las evidencias se refrescan en el mismo acto de staging; ver cifra exacta final
en el cierre de este documento). Incluye los ficheros nuevos ya en staging. Tras F1/F2/8d los
archivos de producto/tests crecieron.

**Producto y tests (diff vs `66448dc`):**

| Archivo | +/− | Rol |
|---|---|---|
| `src/application/services/certification_snapshot.py` | +937 | Productor schema v2: `build_certification_state_v2`, `write_certification_state_v2`, `_frozen_block` (10 keys), reloj NOT_STARTED→START, crash-safe; **F1** envelope v2 completo al START; **8d** preservación del `frozen` anclado |
| `src/application/services/accounting_reconciliation.py` | +646 | **F2** reconciliación three-way con checkpoint/cursor: `BookState` (`entry_fees`, `last_event_ms`), `ReconciliationResult`, `reconcile_with_book` |
| `src/interfaces/cli/paper_runner.py` | +274/−14 | Wiring CLI: `--start-certification`, identidad al START, `default_session_id`, `certification_phase/schema_version` |
| `harness/scripts/safeguard_drill.py` | +517 | Drills por secuencias canónicas (kill_switch/daily_loss), `safeguard_passes` fail-closed |
| `harness/tests/test_safeguard_drill.py` | +193 | Tests del drill |
| `tests/test_certification_snapshot.py` | +1593 | Tests unitarios del productor v2 + regresiones F1 y 8d |
| `tests/test_accounting_reconciliation.py` | +914 | Tests F2 three-way (8 obligatorios) + corrupción compensada |
| `tests/test_cli_paper_runner.py` | +620/−1 | Tests del wiring CLI + regresión F1 deploy fresco + 8d/4-CLI |
| `tests/test_settings.py` | +11 | 3 campos nuevos de settings |
| `tests/e2e/test_certification_state_v2_e2e.py` | +815 | E2E productor→estado→evaluador (E2E-1..10 + caso 9 mid-run fills) |
| `src/settings.py` | +3 | `git_commit`, `docker_image_digest`, `paper_safeguard_evidence_path` |
| `src/version.py` | +1/−1 | `__version__` `0.1.3 → 0.2.0` |
| `pyproject.toml` | +1/−1 | `[project].version` `0.1.0 → 0.2.0` (sana drift pre-existente 0.1.0 vs 0.1.3) |
| `uv.lock` | +1/−1 | lock de la nueva versión |
| `tests/test_version_consistency.py` | +35 | anti-drift (runtime == pyproject == `0.2.0`) |

**Docs / evidencia (entran en el commit):**

- `docs/phases/16c/ledger-16c.md` (+54) — ledger 16c (16c.1..16c.5 COMPLETE · 16c.6 READY_FOR_COMMIT_GATE)
- `docs/phases/16c/commit-candidate-007.md` (este reporte)
- `docs/phases/16c/evidence/log.md` (+39) — índice de evidencia + resumen de gates FINAL
- `docs/phases/16c/post-commit-verification-004.md` (+60), `docs/phases/16c/post-commit-verification-006.md` (+75) — carry-over documental de verificación post-commit
- `docs/superpowers/plans/2026-09-09-paper-certification-state-v2-producer-16c6.md` (+809) — plan SDD (Task 8c F1/F2, Task 8d corrección final)
- Evidencia de gates 16c.6 (en `docs/phases/16c/evidence/`): `full-suite-16c6.log` + `full-suite-coverage-16c6.json`, `harness-suite-16c6.log` + `harness-suite-coverage-16c6.json`, `e2e-certification-state-16c6.log`, `ruff-check-16c6.log`, `ruff-format-16c6.log`, `mypy-16c6.log`, `secret-scan-16c6.log` + `secret-scan-16c6-scope.txt`, `version-consistency-16c6.log`, `alembic-chain-16c6.log`, `alembic-upgrade-head-16c6.log`, `alembic-downgrade-16c6.log`

**Eliminados:** ninguno.

## Diff

```text
# diff 66448dc..staged final: 35 files, +8218 / −18 (exacto tras el re-stage; ver nota final)
 tests/test_certification_snapshot.py                | 1593 +++++++++++++++++++++++++
 src/application/services/certification_snapshot.py  |  937 ++++++++++++++++++++
 tests/test_accounting_reconciliation.py             |  914 +++++++++++++++++++
 tests/e2e/test_certification_state_v2_e2e.py        |  815 ++++++++++++++++++
 docs/superpowers/plans/...-16c6.md                  |  809 ++++++++++++++++++
 src/application/services/accounting_reconciliation.py | 646 +++++++++++++++++
 tests/test_cli_paper_runner.py                      |  620 +++++++++----
 harness/scripts/safeguard_drill.py                  |  517 ++++++++++++++++
 src/interfaces/cli/paper_runner.py                  |  288 +++++++++----
 docs/phases/16c/commit-candidate-007.md             |  271 +++++++++++
 harness/tests/test_safeguard_drill.py               |  193 ++++++++++
 docs/phases/16c/evidence/full-suite-16c6.log        |  165 +++++++
 docs/phases/16c/post-commit-verification-006.md     |   75 +++++
 docs/phases/16c/post-commit-verification-004.md     |   60 +++++
 docs/phases/16c/ledger-16c.md                       |   54 +++
 docs/phases/16c/evidence/log.md                     |   39 +++
 docs/phases/16c/evidence/secret-scan-16c6-scope.txt |   35 +++
 tests/test_version_consistency.py                   |   35 +++
 docs/phases/16c/evidence/harness-suite-16c6.log     |   26 +++
 docs/phases/16c/evidence/alembic-chain-16c6.log     |   15 +++
 docs/phases/16c/evidence/alembic-upgrade-head-16c6.log | 15 +++
 docs/phases/16c/evidence/e2e-certification-state-16c6.log | 13 +++
 docs/phases/16c/evidence/version-consistency-16c6.log |  13 +++
 tests/test_settings.py                              |   11 +++
 docs/phases/16c/evidence/alembic-downgrade-16c6.log |    8 +++
 ... (mypy/ruff/secret-scan logs, coverage json, settings/version/pyproject/uv.lock)
 35 files changed, 8218 insertions(+), 18 deletions(-)
```

Diff completo del paquete (working tree vs base) revisado Task a Task en el ledger del plan
SDD (`.superpowers/sdd/2026-09-09-paper-certification-state-v2-producer-16c6/progress.md`).

## Arquitectura afectada / blast radius

Puertos/contratos de producto tocados (todos consumidos por tests + CLI; sin cambio de
comportamiento del engine):

- `src/application/services/certification_snapshot.py` (nuevo): produce el `certification-state`
  v2. Consumido por `PaperRunner`/CLI. Contrato alineado con `FROZEN_VERSION_KEYS` del evaluador
  (paridad 10 keys testeada por ruta).
- `src/application/services/accounting_reconciliation.py` (nuevo): espejo del accounting del
  engine con **F2 three-way** (live/full/incremental + checkpoint/cursor). Consumido por el
  productor; no modifica `portfolio/engine`.
- `src/interfaces/cli/paper_runner.py`: wiring (nuevos flags, reloj explícito, `default_session_id`
  para F1). Callers de entrada: `src/main.py`, tests CLI.
- `src/settings.py`: 3 campos nuevos con defaults; callers: `tests/conftest.py`,
  `tests/test_settings.py`, `test_observability_server.py`, `test_runtime_preflight.py`.
- `src/version.py`: bump a `0.2.0`; el log estructurado lo inyecta en cada evento.

`detect_changes` (codebase-memory, base `66448dc`, inbound, depth 2):
`changed_files: 35` · `seed_symbols: 374` · `impacted_total: 59` — impacto transitivo sobre
**tests y puntos de entrada** (harness/tests 19, tests/ 36 repartidos en CLI/logging/main/
conftest/dashboard/handlers/observability/preflight, src/interfaces 5, main 2). **Cero**
módulos del dominio (engine, portfolio, risk, strategy) en el conjunto impactado: el cierre
16c añade productor + espejo contable pero no altera la aritmética del engine.

`check_index_coverage` post-re-index (moderate, 3087 nodos / 14440 edges, 0 skipped,
0 parse_partial): `src/...` y `tests/...` tocados → `no_recorded_issue` (metadata_match);
`harness/scripts/safeguard_drill.py`, `tests/e2e/*` y `docs/phases/16c/*` → excluidos del
grafo por diseño (subárboles `not_indexed`), igual que en gates previos.

## Índice del grafo

- [x] Índice re-indexado tras el cambio (`index_repository` moderate → `tmp-opencode-phase-16c-restart-safe`, 3087 nodos / 14440 edges, `parse_partial: 0`, `skipped: 0`)
- [x] `detect_changes since 66448dc` → `impacted_total = 59` (tests + entry points; 0 en dominio)
- [x] `check_index_coverage` sobre cada archivo tocado: `no_recorded_issue` en `src/`+`tests/`; `harness/scripts`, `tests/e2e`, `docs` excluidos por diseño
- [ ] Re-index tras el commit (regla AGENTS.md §4.13) — post-GATE con el controller

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Full producto (`tests/`) + cobertura | **719 passed, 1 skipped** · 93.69% branch | `full-suite-16c6.log`, `full-suite-coverage-16c6.json` |
| Harness (`harness/tests`) + cobertura | **91 passed** · 80.25% branch | `harness-suite-16c6.log`, `harness-suite-coverage-16c6.json` |
| E2E productor→estado→evaluador | **9 passed** (E2E-1..10 + caso 9 mid-run fills; strict JSON lossless caso 8) | `e2e-certification-state-16c6.log` |
| Version consistency (anti-drift) | **3 passed** | `version-consistency-16c6.log` |
| Cadena Alembic | heads+history lineales a `0011`; upgrade head + downgrade −1 OK en DB descartable | `alembic-chain-16c6.log`, `alembic-upgrade-head-16c6.log`, `alembic-downgrade-16c6.log` |

## Cobertura

| Ámbito | Cobertura branch | Umbral | Evidencia |
|---|---|---|---|
| Producto (`src/`) | **93.69%** | 90% | `full-suite-coverage-16c6.json` |
| Arnés (`harness/scripts`) | **80.25%** | 80% | `harness-suite-coverage-16c6.json` |

## Calidad

```bash
uv run ruff check .            # All checks passed!
uv run ruff format --check .   # 268 files already formatted
uv run mypy src tests          # Success: no issues found in 235 source files
uv run pytest                  # 719 passed, 1 skipped
(cd harness && uv run pytest)  # 91 passed
```

## Seguridad

- [x] Secret scan: **0 secretos** sobre los 35 archivos tocados (patrones `BEGIN *PRIVATE KEY`,
      `AKIA[0-9A-Z]{16}`, `gh[pousr]_[0-9A-Za-z]{36}`, `sk-[0-9A-Za-z]{32}`) — scope auditable en
      `secret-scan-16c6-scope.txt`, exit=0
- [x] Sin archivos `.env` ni credenciales en el diff
- [x] Sin cambios en `LIVE_TRADING_ENABLED`, fees, slippage, risk/strategy thresholds ni engine
- [x] Blast radius real de producto de 16c.6 (sin ocultarlo): **sí hay cambios de producto** en
      `src/application/services/certification_snapshot.py`, `src/application/services/accounting_reconciliation.py`,
      `src/interfaces/cli/paper_runner.py`, `src/settings.py`, `src/version.py` y `pyproject.toml`
      (productor v2, reconciliación three-way, wiring del paper-runner, settings de artefacto y bump 0.2.0).
      El resto del diff son tests (`tests/**`, `harness/tests/**`), el drill `harness/scripts/safeguard_drill.py`
      y documentación/evidencia (`docs/**`, `uv.lock`).
- [x] **Sin cambios** en engine/portfolio/risk/strategy/fees/slippage/recovery ni en el evaluador
      (`harness/scripts/paper_certification.py`, entregable cerrado de 16c.4)

## Riesgos

- **Reconciliación espejo del engine (bit-exacta) → F2 three-way**: `reconcile_with_book`
  compara `live == full == incremental` componente a componente (cash/position_qty/avg_entry/
  realized_pnl/fees/equity) con el MISMO mark persistido; el checkpoint (`entry_fees` +
  `last_event_ms`) avanza solo en PASS. Exige replicar el orden float del engine; si un fixture
  revelara una diferencia sistemática pequeña, la resolución es ajustar el ORDEN replicado
  (no tocar el engine). Riesgo registrado no bloqueante.
- **F1 — arranque/deploy fresco**: `start_certification` emite un envelope `schema_version: 2`
  completo al anclar, de modo que la primera escritura periódica NO lo reclasifica como legacy
  ni pisa el reloj v2 (regresión `fresh start → periodic write → operational v2 RUNNING` con
  `state_continuity == PASS`). Mantiene routing por `schema_version` (Task 8b).
- **Reloj explícito NOT_STARTED→START**: el arranque de la certificación es una transición de
  estado deliberada (acción de operador vía `--start-certification`); la escritura periódica NO
  debe re-anclar un estado RUNNING/INVALIDATED activo.
- **Identidad al START (resuelto por Task 8d)**: la identidad pristina (0 eventos) nunca queda
  vacía (`runtime_artifact` cae a config: symbol/timeframe/strategy_version; `missing_start_identity`
  rechaza el START si falta algún campo). Y si una sesión ya anclada/RUNNING recibe después una
  identidad distinta, `_resolve_frozen` **preserva el `frozen` anclado** y el mismatch se reporta
  como `frozen_versions` FAIL **sin re-anclar** — el reloj no se pierde silenciosamente. Cubierto
  por 4 tests de regresión 8d.
- **Drift → frozen_versions**: cualquier drift de los 10 campos congelados ⇒ FAIL en el
  evaluador, sin re-anclar el reloj; `INVALIDATED` solo por invalidación explícita del operador.
- **Corrupción compensada (F2)**: eventos viejos (fee↑ + qty/price↓, equity final bit-igual) se
  detectan porque full rejuega el evento corrupto mientras incremental parte del checkpoint
  validado (full≠incremental en cash/position/fees/avg aunque `equity` coincida). Una corrupción
  compensada contenida **íntegramente en eventos nuevos** posteriores al checkpoint carece de
  referencia de componentes independiente (full==incremental la rejuegan igual): limitación
  estructural documentada del gate three-way, no introducida aquí. El caso 4 E2E (BUY previo al
  cursor) sigue FAIL con `accounting_mismatch`.
- **Libro previo ilegible**: si `previous` contiene `accounting_book` no-null y `from_dict` → `None`,
  el productor hace FAIL-closed (`accounting_status = "FAIL"`, reason `unparseable_accounting_book`,
  critical_error) — nunca baseline silencioso.
- **Paper NO certificado**: el bump 0.2.0 invalida certificaciones 0.1.x; certificar una sesión
  real exige redeploy integrado + sesión ≥ 30 días — fuera de este commit, tras GATE del usuario.

## Deuda técnica

- `progress.yaml`: el alta de entregables 16c (add-phase/mark-done) queda como **carry-over
  post-merge** del tronco (`feature/phase-08-llm-decision-agent`, `3e8d15f`) — prohibido editarlo
  a mano; hoy `progress.py report` muestra Fase 16 `in_progress` 1/5 · 20% (bloqueos del add-phase).
- Minors deferred del ledger SDD (Task 1..8d): no-env-override regression test de los 3 campos
  nuevos; CLI drill FAIL sin test de exit code; restart_persists/rollover con fill sintético;
  `--start-certification` se pierde si `run` es inyectado alternativo; corrupción compensada en
  eventos nuevos (F2); deuda de docs del plan (no es fuente de verdad del código).
  _(Resuelto y por tanto eliminado de esta lista: el fallback legacy en `_run_loop` ya NO depende
  de wiring params — el routing es exclusivamente por `_certification_write_kind`/`schema_version`.)_
- Migración productiva en lenovosrv: **MANUAL post-GATE** (requiere el Postgres de despliegue).

## Mensaje de commit propuesto

```
feat(phase-16c): producer schema v2 restart-safe + bump 0.2.0 (cierre integrado)

- productor real escribe certification-state v2 (frozen 10 keys + operational
  11 campos/counts) crash-safe: fsync + atomic replace, reloj explícito
  NOT_STARTED->START, identidad al START (--start-certification)
- F1: start_certification emite envelope schema_version=2 COMPLETO al anclar
  (session_id/session_started_at/frozen/current/operational/accounting_book),
  evitando que el deploy fresco reclasifique el ancla como legacy
- F2: reconciliación three-way live==full==incremental con checkpoint/cursor
  (entry_fees + last_event_ms); avanza sólo en PASS; detecta corrupción/borrado
  de eventos viejos y nuevos, incluida corrupción compensada (fail-closed)
- 8d: preserva el frozen anclado/RUNNING ante mismatch de identidad
  (symbol/timeframe/versión) => frozen_versions FAIL sin re-anclar; START nunca
  re-ancla un RUNNING (+4 regresiones)
- E2E integrado productor->estado->evaluador PASS (9 tests: E2E-1..10 + caso 9
  mid-run fills): strict JSON lossless, recovery/auditabilidad, paridad 10
  frozen keys por ruta
- safeguard drills por secuencias canónicas (kill_switch 6 pasos, daily_loss 5)
  con matcher fail-closed (harness)
- version 0.2.0 (src/version.py + pyproject.toml) + test anti-drift
  (tests/test_version_consistency.py); invalida certificaciones 0.1.x por diseño
- Paper NO marcado certificado; certificación real = redeploy + sesion >=30d
  (post-GATE del usuario)
- sin cambios en engine/portfolio/risk/strategy/evaluator/accounting core
- alembic: cadena lineal single-head 0011, upgrade head + downgrade -1 OK
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

**estado: READY_FOR_USER_GATE**

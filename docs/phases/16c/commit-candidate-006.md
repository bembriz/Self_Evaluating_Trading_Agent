# Commit Candidate Report — 2026-09-09 · Fase 16c.4 (Paper Certification Gate)

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> GATE 16c.5 APPROVED → procede 16c.4. Subfase de **harness/docs** (sin cambios en `src/`).

## Objetivo

Separar formalmente la **certificación Paper** (integridad operacional) de la validación
estadística (Replay / walk-forward / holdout) y sustituir el gate vigente —que mezclaba
`MIN_TRADES=200`, regímenes y `calendar_days` derivado de fills— por un evaluador determinista
de **13 criterios operacionales independientes**, con evidencia explícita por criterio y
resultado estructurado machine-readable.

Reglas de estado implementadas:

- Un fallo obligatorio ⇒ `overall_status = FAIL`. **Sin promedio ni compensación** entre criterios.
- 30 días = calendario real en UTC: se distinguen `session_started_at`, `certification_started_at`
  y `evaluated_at`; `29d 23h 59m 59s` ⇒ FAIL, `>= 30.0d` ⇒ PASS, sin depender de número de fills.
- `MIN_TRADES=200` eliminado como requisito. `trade_count` = alias legacy de `fill_count`
  (documentado); nunca criterio de certificación.
- Versión/hash congelada (10 campos); cualquier drift ⇒ FAIL, **sin re-anclar el reloj**.
- Estado histórico previo preservado como `INVALIDATED` (no se borra ni reescribe).

## Rama

| Campo | Valor |
|---|---|
| branch | `fix/phase-16c-restart-safe` |
| base commit | `9065563` (16c.5 E2E) |

## Archivos

- **Modificados:**
  - `harness/scripts/paper_certification.py` (+402 / −104)
  - `harness/tests/test_paper_certification.py` (+320 / −142; 28 tests)
  - `docs/phases/16c/evidence/log.md` (+7) — índice de evidencia
- **Creados:**
  - `docs/superpowers/plans/2026-09-09-paper-certification-gate-16c4.md` (+178)
  - `docs/phases/16c/commit-candidate-006.md` (este reporte)
  - `docs/phases/16c/evidence/gate-paper-cert-unit.log`
  - `docs/phases/16c/evidence/gate-harness-suite.log`
  - `docs/phases/16c/evidence/gate-harness-coverage.json`
  - `docs/phases/16c/evidence/gate-full-suite.log`
  - `docs/phases/16c/evidence/gate-full-suite-coverage.json`
  - `docs/phases/16c/evidence/gate-ruff-check.log`
  - `docs/phases/16c/evidence/gate-ruff-format.log`
  - `docs/phases/16c/evidence/gate-mypy.log`
  - `docs/phases/16c/evidence/gate-secret-scan.log`
- **Eliminados:** ninguno

## Diff

`git diff --cached --stat` (staging final): **14 archivos, +1343 / −246**.

```text
 docs/phases/16c/commit-candidate-006.md          |  219 +++++++
 .../16c/evidence/gate-full-suite-coverage.json   |    1 +
 docs/phases/16c/evidence/gate-full-suite.log     |  161 +++++++
 .../16c/evidence/gate-harness-coverage.json      |    1 +
 docs/phases/16c/evidence/gate-harness-suite.log  |   24 +
 docs/phases/16c/evidence/gate-mypy.log           |    6 +
 docs/phases/16c/evidence/gate-paper-cert-unit.log|    6 +
 docs/phases/16c/evidence/gate-ruff-check.log     |    6 +
 docs/phases/16c/evidence/gate-ruff-format.log    |    6 +
 docs/phases/16c/evidence/gate-secret-scan.log    |    6 +
 docs/phases/16c/evidence/log.md                  |    7 +
 .../2026-09-09-paper-certification-gate-16c4.md  |  178 +++++++
 harness/scripts/paper_certification.py           |  506 ++++++++++-----
 harness/tests/test_paper_certification.py        |  462 +++++++------
 14 files changed, 1343 insertions(+), 246 deletions(-)
```

Sin cambios en `src/` (PaperRunner, PaperEngine, RiskEngine, Portfolio, EmaRsiBaseline, fees,
slippage, execution, recovery, decision_context).

## Arquitectura afectada / blast radius

El cambio está **contenido en el arnés** (`harness/scripts` + `harness/tests` + `docs`), que el grafo
`codebase-memory-mcp` excluye por diseño. `detect_changes` (base `9065563`, dirección `inbound`):

- `changed_files: 4` · `seed_symbols: 20` · `impacted_total: 0`

`check_index_coverage`: `harness/scripts` y `docs` son subárboles excluidos; `harness/tests/…`
reporta `no_recorded_issue` (metadata_changed). **El cambio toca 0 módulos del grafo de producto**
(no hay impacto transdutivo sobre `src/`). Conclusión explícita de blast radius: **0 callers externos
afectados** — es un reemplazo de un script de harness consumido únicamente por sus propios tests.

## Índice del grafo

- [x] Índice vigente (`index_status`: 2780 nodos / 12253 edges, `generation_matches` = true; sin re-index
  necesaria porque `src/` no cambió y `harness/` está excluido por diseño).
- [x] `check_index_coverage` sobre archivos tocados: `harness/scripts` y `docs` excluidos por diseño;
  `harness/tests` sin `parse_partial`.
- [x] `detect_changes` → `impacted_total = 0` (blast radius nulo sobre el producto).

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Unit gate (`test_paper_certification.py`) | **28 passed** | `gate-paper-cert-unit.log` |
| Arnés completo (`harness/tests`) | **83 passed** | `gate-harness-suite.log` |
| Full suite producto (`tests/`) | **594 passed, 1 skipped** | `gate-full-suite.log` |

### Cobertura de requisitos (TDD RED→GREEN)

| # | Requisito obligatorio | Test | Resultado |
|---|---|---|---|
| 1 | 29 días + todo correcto ⇒ FAIL | `test_29_days_all_correct_fails` | PASS |
| 2 | 30 días + 0 fills + operacional OK ⇒ PASS | `test_30_days_zero_fills_passes` | PASS |
| 3 | 30 días + 1 fill ⇒ puede PASS | `test_30_days_one_fill_can_pass` | PASS |
| 4 | 30 días + 500 fills ⇒ no concede PASS por sí mismo | `test_500_fills_do_not_grant_pass_by_themselves` | PASS |
| 5 | residual != 0 ⇒ FAIL | `test_accounting_residual_nonzero_fails` | PASS |
| 6 | gap no explicado ⇒ FAIL | `test_unexplained_gap_fails` | PASS |
| 7 | decision_context incompleto ⇒ FAIL | `test_missing_decision_context_fails` | PASS |
| 8 | metrics history < 30d ⇒ FAIL | `test_metrics_history_short_fails` | PASS |
| 9 | version drift ⇒ FAIL | `test_version_drift_fails` | PASS |
| 10 | recovery integrity falla ⇒ FAIL | `test_recovery_integrity_failure_fails` | PASS |
| 11 | critical error sin explicar ⇒ FAIL | `test_critical_error_unexplained_fails` | PASS |
| 12 | critical error explicado ⇒ PASS (definido y testeado) | `test_critical_error_explicitly_explained_passes` | PASS |
| 13 | legacy certification-state ⇒ lectura compatible | `test_legacy_certification_state_reads_compatibly` | PASS |
| 14 | MIN_TRADES=200 ausente ⇒ no bloquea | `test_min_trades_absent_does_not_block_paper` | PASS |

Adicionales: `29d23h59m59s` ⇒ FAIL (`test_29d23h59m59s_fails`), drift de `certification_started_at`
sin re-anclar reloj (`test_certification_started_at_drift_fails_without_resetting_clock`),
sin promedio (`test_no_averaging_each_mandatory_failure_reported`), estructura machine-readable
(`test_report_is_machine_readable`), INVALIDATED preservado (`test_invalidated_status_is_preserved`,
`test_invalidate_state_does_not_rewrite_previous_evidence`), CLI markdown+json, corrupt JSON, invalidate.

## Cobertura

| Ámbito | Cobertura branch | Umbral | Evidencia |
|---|---|---|---|
| Arnés (`harness/scripts`) | **81.75%** | 80% | `gate-harness-coverage.json` |
| Producto (`src/`) | **94.39%** | 90% | `gate-full-suite-coverage.json` |

`paper_certification.py` cubierto al 88% (líneas no cubiertas: ramas defensivas de parseo de
timestamp/número, `__main__` y el report INVALIDATED vía CLI).

## Calidad

```bash
uv run ruff check .             # All checks passed
uv run ruff format --check .    # 260 files already formatted
uv run mypy src tests           # Success: no issues found in 229 source files
uv run pytest -q                # 594 passed, 1 skipped
(cd harness && uv run pytest)   # 83 passed
```

## Seguridad

- [x] Sin secretos en el diff (solo arnés: script + tests + docs; `docker_image_digest` es placeholder `sha256:testdigest`)
- [x] Sin archivos `.env` ni credenciales
- [x] Secret scan limpio (`gate-secret-scan.log`, exit=0)
- [x] Sin cambios en `LIVE_TRADING_ENABLED`, fees, slippage, strategy/risk versiones ni threshold de riesgo

## Riesgos

- El evaluador define un **esquema v2** de estado (frozen/current/operational) que el runner 0.1.x aún
  no escribe; lee legacy sin error (test 13). La producción que escribirá v2 es trabajo posterior (0.2.0),
  fuera de este commit.
- `accounting_residual == 0` se exige **exacto**: el productor 0.2.0 debe normalizar a 0 (hoy la
  reconciliación ya emite `EXACT_ZERO`).
- `INVALIDATED` queda reservado al estado histórico explícito; el drift de versiones es `FAIL` (no
  `INVALIDATED`), coherente con el caso TDD nº 9. El operador invalida vía `--invalidate` para archivar
  y reiniciar certificación.

## Deuda técnica

- El runner (`src/application/services/paper_runner.py`) sigue escribiendo `trade_count` (legacy =
  `fill_count`) y `calendar_days` derivado; migrarlo al esquema v2 es requisito obligatorio del
  cierre integrado (sección siguiente).
- `evaluate_state`/`CertificationResult` (API antigua) fueron reemplazados por
  `evaluate_certification`/`CertificationReport`; ningún otro script del arnés importaba la API antigua.

## Requisito obligatorio del cierre integrado (16c/0.2.0)

> **NO se implementa dentro de 16c.4.** Este commit solo entrega el evaluador del gate
> operacional y sus tests. El wiring productor→estado→evaluador pertenece al **cierre
> integrado 16c/0.2.0** y es requisito bloqueante **antes de cualquier deployment /
> nueva Paper Certification**:

- [ ] El `PaperRunner`/productor debe emitir el `certification-state` con **schema v2**
      (`frozen`/`current`/`operational` + timestamps reales UTC en `session_started_at` /
      `certification_started_at`); hoy sigue escribiendo el formato legacy.
- [ ] Un **E2E integrado productor→estado→evaluador** debe dar **PASS**: el estado v2 emitido
      por el runner debe alimentar `evaluate_certification` (este gate) y superar todos los
      criterios operacionales en una sesión válida de ≥ 30 días.

Sin ese requisito, evaluar una sesión real con el gate 16c.4 producirá `FAIL` por evidencia
ausente (campos v2 no emitidos) — comportamiento correcto y esperado.

## Versionado

`strategy_version = baseline-v1` · `risk_config_version = risk-v1` · `application_version` sin bump
(bump `0.2.0` queda bloqueado hasta redeploy integrado, fuera de este gate).

## Mensaje de commit propuesto

```
feat(phase-16c): paper certification operational gate (separar Replay de Paper)

- evaluador determinista de 13 criterios operacionales independientes, sin
  promedio ni compensación; un fallo obligatorio => FAIL
- 30 días reales en UTC (session_started_at / certification_started_at /
  evaluated_at); 29d23h59m59s => FAIL
- elimina MIN_TRADES=200; trade_count = alias legacy de fill_count (documentado),
  no es criterio de certificación
- freeze de 10 campos (git_commit, versions, docker digest, symbol, timeframe,
  initial_capital, fees/slippage, certification_started_at); drift => FAIL sin
  re-anclar reloj
- resultado estructurado (overall_status, evaluated_at, certification_age_days,
  checks[], failure_reasons[]) + reporte JSON machine-readable
- estado histórico preservado como INVALIDATED (no se reescribe)
- sin cambios en src/ (PaperRunner/PaperEngine/RiskEngine/Portfolio/estrategia)
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

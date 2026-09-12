# Commit Candidate Report — 2026-09-12

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> Preparado para el gate humano de la Fase 18B. Nada está staged ni commiteado.

## Objetivo

Añadir la evaluación económica DEVELOPMENT de la Fase 18B: comparar
`baseline-v1` contra `EmaRsiBtcContext-v1` sobre TODO DEVELOPMENT `[0, 62208)`
con datos congelados, PaperEngine/RiskEngine reales, identidad experimental
independiente, persistencia en `ExperimentRegistry`, reproducibilidad por
double-run y atribución del filtro BTC, sin tocar WALK_FORWARD ni FINAL_HOLDOUT.

## Rama

| Campo | Valor |
|---|---|
| branch | `feature/phase-08-llm-decision-agent` |
| base commit | `e0212edcee08c02615a16d4731ccc5346c89f3c4` |
| staging | none (`git diff --cached --exit-code` PASS) |

## Archivos

- **Creados (código/tooling):**
  - `src/lab/development_evaluation.py` (81 statements)
  - `harness/scripts/phase18b_development_evaluation.py` (453 líneas)
- **Creados (tests):**
  - `tests/lab/test_development_evaluation.py`
  - `tests/integration/test_development_evaluation_integration.py`
  - `tests/e2e/test_phase18b_development_evaluation_e2e.py`
- **Creados (evidencia):** `docs/phases/18B/evidence/` (comparison JSON+MD,
  registry, coverage JSON, logs de tests/ruff/format/mypy/holdout/staging).
- **Modificados:** ninguno.
- **Eliminados:** ninguno.

## Diff

Todos los archivos 18B son nuevos y no rastreados. No hay cambios sobre archivos
de producto existentes; `git diff --cached` está vacío.

```text
src/lab/development_evaluation.py                       | 171 líneas
harness/scripts/phase18b_development_evaluation.py      | 453 líneas
tests/lab/test_development_evaluation.py                | 245 líneas
tests/integration/test_development_evaluation_integration.py | 188 líneas
tests/e2e/test_phase18b_development_evaluation_e2e.py   | 103 líneas
docs/phases/18B/evidence/*                              | evidencia
```

## Arquitectura afectada

Un módulo lab puro y nuevo (`lab.development_evaluation`) reutiliza sin
duplicar fórmulas: `domain.evaluation.metrics.compute_metrics` y
`lab.walk_forward.trades_from_trace` (solo helper puro; no se ejecutan ventanas
walk-forward). El script de harness cablea `FrozenDatasetAdapter` +
`LabSessionRunner` + `PaperEngine` + `RiskEngine` reales, `ExperimentSpec`/
`ExperimentRegistry` y `KernelIdentity`.

Blast radius (`detect_changes`, base `e0212ed`): solo dependencias salientes
hacia símbolos existentes; **cero símbolos de producto modificados** y **cero
callers externos**. `docs/phases/18B/`, `src/lab/development_evaluation.py` y los
tests nuevos son los únicos cambios 18B; el resto de `changed_files` es trabajo
preexistente ajeno.

## Índice del grafo

- [x] Watcher re-indexó el worktree (generación `2026-09-12T19:57:19Z`,
      `nodes=11791`, `edges=29129`, HEAD `e0212ed`).
- [x] `check_index_coverage` sin issues registrados sobre módulo, script, tests y
      evidencia 18B.
- [ ] Re-index post-commit: pendiente tras la autorización.

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Lab | 297 passed | `docs/phases/18B/evidence/tests-lab.log` |
| Integration | 27 passed | `docs/phases/18B/evidence/tests-integration.log` |
| E2E | 6 passed | `docs/phases/18B/evidence/tests-e2e.log` |
| Global | 755 passed, 1 skipped | `docs/phases/18B/evidence/coverage-global.log` |
| Módulo 18B | 15 passed | `docs/phases/18B/evidence/coverage-18b.log` |

## Cobertura

- Global combined statement/branch: `96.00%` (umbral 90% superado).
- Módulo nuevo `src/lab/development_evaluation.py`: statements `81/81` (`100%`),
  branches `26/26` (`100%`).
- Evidencia: `docs/phases/18B/evidence/coverage.json` y `coverage-18b.json`.

## Resultado DEVELOPMENT

| Métrica | baseline-v1 | EmaRsiBtcContext-v1 | delta |
|---|---|---|---|
| closed_trades | 406 | 391 | -15 |
| net_pnl | -20.023554 | -20.000759 | +0.022795 |
| return_pct | -0.020024 | -0.020001 | +0.000023 |
| fees | 16.242716 | 15.641898 | -0.600818 |
| slippage | 3.248543 | 3.128380 | -0.120164 |
| max_drawdown | 0.016775 | 0.016872 | +0.000097 |
| profit_factor | 0.390291 | 0.402466 | +0.012175 |
| expectancy | -0.049319 | -0.051153 | -0.001834 |
| win_rate | 0.083744 | 0.084399 | +0.000655 |
| average_win | 0.376988 | 0.408224 | +0.031236 |
| average_loss | -0.088283 | -0.093498 | -0.005215 |

Atribución BTC: `baseline_buy_candidates=634`, `btc_confirmed_buys=421`,
`btc_blocked_buys=213` (identidad 634 = 421 + 213). De los 137 BUY bloqueados que
el baseline sí ejecutó: 11 ganadores y 126 perdedores, net `-5.403646`
(descriptivo; no se alteran decisiones).

Clasificación predeclarada: `DEVELOPMENT_RESULT=MIXED` (mejoran PF y net PnL,
empeora ligeramente expectancy; drawdown dentro del umbral material).
`WALK_FORWARD_CANDIDATE=NO` con el criterio fijado (solo `IMPROVED` → `YES`).

## Calidad

```bash
uv run ruff check .        # PASS - docs/phases/18B/evidence/ruff.log
uv run ruff format --check . # PASS - docs/phases/18B/evidence/format.log
uv run mypy src tests      # PASS - docs/phases/18B/evidence/mypy.log
uv run pytest --cov=src    # 755 passed, 1 skipped, 96.00% - coverage-global.log
```

## Seguridad

- [x] Sin credenciales, tokens, claves, contraseñas ni connection strings.
- [x] Sin `.env` ni certificados; secret scan sobre los archivos nuevos limpio.
- [x] Nada staged (`docs/phases/18B/evidence/no-staging.log`).

## Holdout / Walk-forward

- `WALK_FORWARD_READS=0` (nunca se solicita `[62208, 88128)`).
- `FINAL_HOLDOUT_READS=0`, `FINAL_HOLDOUT_EXECUTIONS=0`.
- `HOLDOUT_STATE=PRISTINE` (`docs/phases/18B/evidence/holdout-state.log`).
- Runtime protegido intacto: `protected-runtime-diff.log` exit 0.

## Riesgos

- Development puede orientar la selección, pero NO demuestra edge out-of-sample:
  `EDGE_PRESENT=NOT_EVALUATED_OUT_OF_SAMPLE`, `STRATEGY_PROMOTABLE=NOT_EVALUATED`.
- El resultado es `MIXED` y ambas estrategias siguen con expectancy y PF < 1;
  ninguna es candidata a walk-forward bajo el criterio predeclarado.
- La atribución de BUY bloqueados es descriptiva y no ajusta parámetros.

## Deuda técnica

- Sin deuda funcional nueva. La evaluación económica completa
  (walk-forward/estadística) permanece explícitamente fuera de 18B.
- `signals_buy`/`fills` se muestran con formato decimal en el delta del Markdown
  (cosmético).

## Interpretación humana (2026-09-12)

`DEVELOPMENT_RESULT=MIXED` (no reinterpretar como IMPROVED):

- PnL mejora marginalmente (`-20.023554` → `-20.000759`).
- Profit Factor mejora marginalmente (`0.390291` → `0.402466`).
- Expectancy empeora (`-0.049319` → `-0.051153`).
- Max drawdown empeora ligeramente (`0.016775` → `0.016872`).
- La reducción de costes explica parte importante de la mejora económica
  (fees `-0.600818`, slippage `-0.120164`).
- No existe evidencia suficiente para gastar WALK_FORWARD.

`WALK_FORWARD_CANDIDATE=NO` · `STRATEGY_PROMOTABLE=NO` ·
`EDGE_PRESENT=NOT_EVALUATED_OUT_OF_SAMPLE`.

Atribución del filtro BTC (solo descriptiva): `baseline_buy_candidates=634`,
`btc_confirmed_buys=421`, `btc_blocked_buys=213`; del subconjunto bloqueado que el
baseline sí ejecutó (137): 11 ganadores y 126 perdedores. Bloquear una entrada
cambia la trayectoria posterior del portfolio, por lo que **no** se afirma
causalmente que el filtro "eliminó 126 trades perdedores"; es una lectura
descriptiva, no un contrafactual perfecto.

## Mensaje de commit propuesto

```text
feat(lab): add development economic comparison for BTC context (18B)

- add pure development_evaluation helpers (metrics, deltas, attribution, predeclared classification)
- add phase18b harness script over [0,62208) with real engine, registry and double-run
- add unit/integration/e2e tests and DEVELOPMENT comparison evidence
```

---

**DECISIÓN DEL USUARIO:** ☑ APPROVED → ejecutar commit · 2026-09-12 (HUMAN COMMIT GATE 18B)

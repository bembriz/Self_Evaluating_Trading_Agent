# Commit Candidate Report — 2026-09-12

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> Preparado para el gate humano de la Fase 18D. Nada está staged ni commiteado.

## Objetivo

Evaluación económica DEVELOPMENT de tres estrategias sobre `[0, 62208)` con
runtime-parity real: `baseline-v1` (A), `EmaRsiBtcContext-v1` (B) y
`EmaRsiBtcRegime-v1` (C). Comparación primaria C vs A (determina
`DEVELOPMENT_RESULT` y `WALK_FORWARD_CANDIDATE`) y comparación secundaria C vs B
(valor incremental del slope BTC). Sin walk-forward ni holdout.

## Rama

| Campo | Valor |
|---|---|
| branch | `feature/phase-08-llm-decision-agent` |
| base commit | `ce7f2f32b251174f2d663b9a9b573fe0e2836f0f` (18C committed) |
| staging | none (`git diff --cached --exit-code` PASS) |

## Archivos

- **Creados (tooling):**
  - `harness/scripts/phase18d_development_evaluation.py` (555 líneas)
- **Creados (tests):**
  - `tests/integration/test_phase18d_development_evaluation_integration.py`
  - `tests/e2e/test_phase18d_development_evaluation_e2e.py`
- **Creados (evidencia):** `docs/phases/18D/evidence/` (comparison JSON+MD,
  registry de 3 specs y 4 runs, coverage, logs de tests/ruff/format/mypy/
  holdout/staging).
- **Modificados / eliminados:** ninguno. No se tocó ningún artefacto de 18B;
  se reutilizan los helpers puros de `lab.development_evaluation`.

## Diff

Todos los archivos 18D son nuevos y no rastreados. `git diff --cached` vacío.

```text
harness/scripts/phase18d_development_evaluation.py            | 555 líneas
tests/integration/test_phase18d_development_evaluation_integration.py | 221 líneas
tests/e2e/test_phase18d_development_evaluation_e2e.py         | 116 líneas
docs/phases/18D/evidence/*                                    | evidencia + registry
```

## Arquitectura afectada

Script de harness nuevo que reutiliza los helpers puros ya validados de
`lab.development_evaluation` (`count_signals`, `session_metrics`,
`compare_metrics`, `btc_filter_attribution`, `classify_development_result`) y el
runtime real (`FrozenDatasetAdapter` + `LabSessionRunner` + `PaperEngine` +
`RiskEngine`). No crea módulo `src` nuevo ni framework nuevo. No modifica
`EmaRsiBaseline`, `EmaRsiBtcContext-v1`, `EmaRsiBtcRegime-v1`, `LabSessionRunner`
ni runtime protegido.

`check_index_coverage` (generación `2026-09-12T21:31:38Z`): script, tests y
evidencia sin issues registrados.

## Índice del grafo

- [x] Índice refrescado tras la implementación.
- [x] `check_index_coverage` sin issues sobre los archivos 18D.
- [ ] Re-index post-commit: pendiente tras autorización.

## Resultado DEVELOPMENT (full `[0, 62208)`)

SpecIds:
- baseline-v1: `2a9b4abda1ef24d1ef854c0614b8bc97e38d532860b9bccf228f806343e6db4e`
- EmaRsiBtcContext-v1: `57ecf38f4f7e26355231414906375ea1b43d2e2a0d6ba2e3e773dff94789015f`
- EmaRsiBtcRegime-v1: `02d4c0019fd735a24451f0b065e762c73423af9717097056dc20c122152184c9`

| Métrica | baseline-v1 | Context-v1 | Regime-v1 | Regime vs Baseline | Regime vs Context |
|---|---|---|---|---|---|
| closed_trades | 406 | 391 | 391 | -15 | 0 |
| net_pnl | -20.023554 | -20.000759 | -19.646087 | +0.377467 | +0.354672 |
| return_pct | -0.020024 | -0.020001 | -0.019646 | +0.000377 | +0.000355 |
| fees | 16.242716 | 15.641898 | 15.642253 | -0.600463 | +0.000355 |
| slippage | 3.248543 | 3.128380 | 3.128451 | -0.120093 | +0.000071 |
| max_drawdown | 0.016775 | 0.016872 | 0.016518 | -0.000257 | -0.000355 |
| profit_factor | 0.390291 | 0.402466 | 0.413466 | +0.023176 | +0.011000 |
| expectancy | -0.049319 | -0.051153 | -0.050246 | -0.000927 | +0.000907 |
| win_rate | 0.083744 | 0.084399 | 0.092072 | +0.008328 | +0.007673 |

Atribución del filtro (descriptiva): `BASELINE_BUY_CANDIDATES=634`,
`CONTEXT_CONFIRMED_BUYS=421`, `REGIME_CONFIRMED_BUYS=391`,
`REGIME_BLOCKED_BUYS=243` (identidad 634 = 391 + 243),
`ADDITIONAL_BUYS_BLOCKED_BY_SLOPE=30` (421 - 391).

Clasificación predeclarada:
- **PRIMARY C vs A = `MIXED`**: mejoran profit factor y net PnL, pero empeora
  expectancy; drawdown mejora. No se reinterpreta como IMPROVED.
- **SECONDARY C vs B = `IMPROVED`**: expectancy, profit factor y net PnL mejoran
  y drawdown mejora. El slope aporta valor incremental frente al gate
  `EMA20 > EMA50`, medido solo de forma descriptiva dentro de DEVELOPMENT.

`WALK_FORWARD_CANDIDATE=NO` (solo `IMPROVED` primario habilitaría el gate).

## Reproducibilidad

`REPRODUCIBILITY=PASS`: mismo `REGIME_SPEC_ID`, distinto `RunId`,
`event_trace_hash` y `metrics_hash` idénticos.

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Lab | 326 passed | `docs/phases/18D/evidence/tests-lab.log` |
| Integration | 38 passed | `docs/phases/18D/evidence/tests-integration.log` |
| E2E | 11 passed | `docs/phases/18D/evidence/tests-e2e.log` |
| Global | 800 passed, 1 skipped | `docs/phases/18D/evidence/coverage-global.log` |

Cobertura cubierta: condiciones económicas idénticas, slice DEVELOPMENT
completo, alineación BTC, SpecId de regime distinto, métricas y comparación
deterministas, identidad de atribución, clasificación predeclarada,
WALK_FORWARD no leído, FINAL_HOLDOUT no leído, holdout `PRISTINE`.

## Cobertura

- Global combined statement/branch: `96.08%` (umbral 90% superado).
- Sin módulo Python nuevo de 18D (solo harness/tests), por lo que no aplica el
  requisito de 100% de módulo nuevo.

## Calidad

```bash
uv run ruff check .          # PASS - docs/phases/18D/evidence/ruff.log
uv run ruff format --check . # PASS - docs/phases/18D/evidence/format.log
uv run mypy src tests        # PASS - docs/phases/18D/evidence/mypy.log
uv run pytest --cov=src      # 800 passed, 1 skipped, 96.08% - coverage-global.log
```

## Seguridad

- [x] Sin credenciales, tokens, claves ni connection strings.
- [x] Sin `.env` ni certificados.
- [x] Nada staged (`docs/phases/18D/evidence/no-staging.log`).

## Data safety

- `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0`, `FINAL_HOLDOUT_EXECUTIONS=0`.
- `HOLDOUT_STATE=PRISTINE` (`docs/phases/18D/evidence/holdout-state.log`).
- Runtime protegido intacto (`protected-runtime-diff.log` exit 0).

## Disciplina experimental

`EmaRsiBtcContext-v1` y `EmaRsiBtcRegime-v1` son hipótesis distintas evaluadas
sobre DEVELOPMENT. No se introduce una tercera variante BTC ni se cambia
`lookback=4` a partir de estos resultados. Si C no pasa el gate primario, la
estrategia queda cerrada con ese resultado.

## Riesgos

- DEVELOPMENT no demuestra edge out-of-sample: `EDGE_PRESENT` y
  `STRATEGY_PROMOTABLE` permanecen `NOT_EVALUATED`.
- La mejora secundaria C vs B es descriptiva y no habilita walk-forward por sí
  sola.
- La atribución de BUY bloqueados no es un contrafactual causal perfecto.

## Deuda técnica

- Sin deuda funcional nueva. La comparación de 3 estrategias duplica helpers de
  formato JSON/Markdown del script 18B (deliberado para no refactorizar 18B).

## Interpretación humana (2026-09-12)

PRIMARY `EmaRsiBtcRegime-v1` vs `baseline-v1` → `DEVELOPMENT_RESULT=MIXED`
(no reinterpretar como IMPROVED):

- Net PnL mejora (`-20.023554` → `-19.646087`).
- Profit Factor mejora (`0.390291` → `0.413466`).
- Max drawdown mejora ligeramente (`0.016775` → `0.016518`).
- Expectancy empeora (`-0.049319` → `-0.050246`).

Por la regla predeclarada, expectancy es una de las tres métricas económicas
primarias y no mejora ⇒ MIXED.

SECONDARY `EmaRsiBtcRegime-v1` vs `EmaRsiBtcContext-v1` →
`INCREMENTAL_RESULT_VS_CONTEXT=IMPROVED` (descriptivo: el slope aporta valor
incremental sobre `EMA20 > EMA50` dentro de DEVELOPMENT).

Decisión de promoción:

`WALK_FORWARD_CANDIDATE=NO` · `STRATEGY_PROMOTABLE=NO` ·
`EDGE_PRESENT=NOT_EVALUATED_OUT_OF_SAMPLE` · `WALK_FORWARD_AUTHORIZED=NO`.
No se ejecuta walk-forward.

Disciplina experimental: `EmaRsiBtcContext-v1` y `EmaRsiBtcRegime-v1` fueron
dos hipótesis distintas evaluadas sobre DEVELOPMENT. No se crean ni evalúan en
esta fase `slope lookback` 3/5/8, thresholds alternativos ni nuevas
combinaciones EMA, y no se hace tuning adicional de esta familia con
DEVELOPMENT.

## Mensaje de commit propuesto

```text
feat(lab): evaluate BTC regime candidate on development (18D)

- evaluate baseline-v1, EmaRsiBtcContext-v1 and EmaRsiBtcRegime-v1 on [0,62208)
- reuse 18B pure helpers; primary C vs A classification and secondary C vs B deltas
- add integration/e2e coverage and full evidence with registry
```

---

**DECISIÓN DEL USUARIO:** ☑ APPROVED → ejecutar commit · 2026-09-12 (HUMAN COMMIT GATE 18D)

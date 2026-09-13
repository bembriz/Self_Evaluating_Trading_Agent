# Commit Candidate Report — 2026-09-13

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> Preparado para el gate humano de la Fase 19B. Nada está staged ni commiteado.

## Objetivo

Evaluación económica DEVELOPMENT de `EthDonchianBreakout-v1` (B) contra
`baseline-v1` (A) sobre `[0, 62208)` con runtime-parity real, identidad
experimental independiente, persistencia en `ExperimentRegistry`,
reproducibilidad por double-run, atribución señal/ejecución, diagnósticos
ADX/breakout y métricas de estructura de trade. Sin walk-forward ni holdout.

## Rama

| Campo | Valor |
|---|---|
| branch | `feature/phase-08-llm-decision-agent` |
| base commit | `c82226ff863eda1b8e4b96db6f390e5a614a0e0d` (19A committed) |
| staging | none (`git diff --cached --exit-code` PASS) |

## Archivos

- **Creados (tooling):** `harness/scripts/phase19b_development_evaluation.py`
- **Creados (tests):**
  - `tests/integration/test_phase19b_development_evaluation_integration.py`
  - `tests/e2e/test_phase19b_development_evaluation_e2e.py`
- **Creados (evidencia):** `docs/phases/19B/evidence/` (comparison JSON+MD,
  registry de 2 specs y 3 runs, coverage, logs de tests/ruff/format/mypy/
  holdout/staging).
- **Modificados / eliminados:** ninguno. No se toca ningún artefacto de 18B/18D;
  se reutilizan los helpers puros de `lab.development_evaluation`. No se modifica
  `adx` ni `EthDonchianBreakout-v1` durante la evaluación.

## Diff

Todos los archivos 19B son nuevos y no rastreados. `git diff --cached` vacío.

```text
harness/scripts/phase19b_development_evaluation.py             | 565 líneas
tests/integration/test_phase19b_development_evaluation_integration.py | 151 líneas
tests/e2e/test_phase19b_development_evaluation_e2e.py          | 123 líneas
docs/phases/19B/evidence/*                                     | evidencia + registry
```

## Arquitectura afectada

Script de harness nuevo que reutiliza los helpers puros ya validados
(`count_signals`, `session_metrics`, `compare_metrics`,
`classify_development_result`) y el runtime real (`FrozenDatasetAdapter` +
`LabSessionRunner` + `PaperEngine` + `RiskEngine`). Añade, sin framework nuevo:
atribución señal/ejecución, diagnósticos ADX/breakout y métricas de estructura de
trade derivadas de `lab.walk_forward.trades_from_trace`. No crea módulo `src`
nuevo. No modifica runtime protegido ni las estrategias congeladas.

`check_index_coverage` (generación `2026-09-13T00:09:43Z`): sin issues.

## Índice del grafo

- [x] Índice refrescado tras la implementación.
- [x] `check_index_coverage` sin issues sobre los archivos 19B.
- [ ] Re-index post-commit: pendiente tras autorización.

## Resultado DEVELOPMENT (full `[0, 62208)`)

SpecIds:
- baseline-v1: `8979ff8479d9e17ccc17da52f81f1fe25d7c83b5a69419257f307a151929da67`
- EthDonchianBreakout-v1: `9fa8f8e4a67da2e742e89c8bac74145e5bac02937f7e5b94b5363ee382216e45`

| Métrica | baseline-v1 | EthDonchianBreakout-v1 | Delta |
|---|---|---|---|
| signals_buy | 634 | 2035 | +1401 |
| signals_sell | 1021 | 4005 | +2984 |
| fills | 812 | 812 | 0 |
| closed_trades | 406 | 406 | 0 |
| net_pnl | -20.023554 | -20.008372 | +0.015181 |
| return_pct | -0.020024 | -0.020008 | +0.000015 |
| fees | 16.242716 | 16.242731 | +0.000015 |
| slippage | 3.248543 | 3.248546 | +0.000003 |
| max_drawdown | 0.016775 | 0.017006 | +0.000231 |
| profit_factor | 0.390291 | 0.422239 | +0.031948 |
| expectancy | -0.049319 | -0.049282 | +0.000037 |
| win_rate | 0.083744 | 0.105911 | +0.022167 |
| average_win | 0.376988 | 0.340058 | -0.036930 |
| average_loss | -0.088283 | -0.095402 | -0.007119 |

Clasificación predeclarada vs `baseline-v1`:

- **`DEVELOPMENT_RESULT=IMPROVED`**: expectancy (+0.000037), profit factor
  (+0.031948) y net PnL (+0.015181) mejoran; max drawdown empeora solo
  +0.000231, muy por debajo del umbral material de `0.01`.
- `WALK_FORWARD_CANDIDATE=YES` (solo `IMPROVED` habilita el gate), **no
  ejecutado**: se detiene para autorización humana.

## Atribución señal / ejecución (EthDonchianBreakout-v1)

- `DONCHIAN_BUY_SIGNALS=2035`, `DONCHIAN_SELL_SIGNALS=4005`.
- `EXECUTED_BUYS=406`, `EXECUTED_SELLS=406`.
- `REJECTED_BUYS=1629` (posición ya abierta, autoridad del RiskEngine).
- `SELL_SIGNALS_WITHOUT_POSITION=1237`.
- `SUPERSEDED_BUYS=0` (identidad: 406 + 1629 + 0 = 2035).

## Diagnósticos ADX / breakout (descriptivos)

- `RAW_BREAKOUT_EVENTS=2970`.
- `BREAKOUTS_CONFIRMED_BY_ADX=2035`.
- `BREAKOUTS_BLOCKED_BY_ADX=935` (identidad 2970 = 2035 + 935).
- Diagnóstico únicamente; `ADX_MIN` no se ajusta a partir de estos resultados.

## Estructura de trade

| Métrica | baseline-v1 | EthDonchianBreakout-v1 |
|---|---|---|
| average_holding_duration_ms | 8264039.409 | 7040394.089 |
| median_holding_duration_ms | 900000.0 | 900000.0 |
| average_trade_pnl | -0.049319 | -0.049282 |
| largest_win | 2.403399 | 1.257031 |
| largest_loss | -0.419478 | -0.494060 |

Derivadas de la traza de fills existente (`trades_from_trace`); sin framework de
analítica nuevo.

## Reproducibilidad

`REPRODUCIBILITY=PASS`: mismo `DONCHIAN_SPEC_ID`, distinto `RunId`,
`event_trace_hash` y `metrics_hash` idénticos.

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Lab | 351 passed | `docs/phases/19B/evidence/tests-lab.log` |
| Integration | 43 passed | `docs/phases/19B/evidence/tests-integration.log` |
| E2E | 16 passed | `docs/phases/19B/evidence/tests-e2e.log` |
| Global | 844 passed, 1 skipped | `docs/phases/19B/evidence/coverage-global.log` |

Cubierto: condiciones económicas idénticas, slice DEVELOPMENT completo, SpecIds
distintos, métricas deterministas, doble corrida reproducible, regla de
clasificación, identidad de diagnósticos, contabilidad señal vs ejecución,
WALK_FORWARD no leído, FINAL_HOLDOUT no leído, holdout `PRISTINE`.

## Cobertura

- Global combined statement/branch: `96.17%` (umbral 90% superado).
- Sin módulo Python nuevo de 19B (solo harness/tests), por lo que no aplica el
  requisito de 100% de módulo nuevo.

## Calidad

```bash
uv run ruff check .          # PASS - docs/phases/19B/evidence/ruff.log
uv run ruff format --check . # PASS - docs/phases/19B/evidence/format.log
uv run mypy src tests        # PASS - docs/phases/19B/evidence/mypy.log
uv run pytest --cov=src      # 844 passed, 1 skipped, 96.17% - coverage-global.log
```

## Seguridad

- [x] Sin credenciales, tokens, claves ni connection strings.
- [x] Sin `.env` ni certificados.
- [x] Nada staged (`docs/phases/19B/evidence/no-staging.log`).

## Data safety

- `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0`, `FINAL_HOLDOUT_EXECUTIONS=0`.
- `HOLDOUT_STATE=PRISTINE` (`docs/phases/19B/evidence/holdout-state.log`).
- Runtime protegido intacto (`protected-runtime-diff.log` exit 0).
- `adx` y `EthDonchianBreakout-v1` sin cambios (`adx-strategy-frozen.log` exit 0).

## Disciplina experimental

No se evaluaron variantes (Donchian 15/5, 30/15; ADX 15/25/30; sin ADX; filtro
BTC; LLM; multi-timeframe). Parámetros congelados desde 19A. Un segundo candidato
Donchian no se evalúa en esta fase.

## Riesgos

- DEVELOPMENT no demuestra edge out-of-sample: `EDGE_PRESENT` y
  `STRATEGY_PROMOTABLE` permanecen `NOT_EVALUATED`.
- `IMPROVED` es marginal en expectancy/net PnL; no habilita ninguna conclusión de
  rentabilidad. El walk-forward requiere autorización humana explícita.

## Deuda técnica

- Sin deuda funcional nueva. El script 19B duplica helpers de formato
  JSON/Markdown de 18D (deliberado para no refactorizar 18B/18D).

## Interpretación humana (2026-09-13)

Se preserva el resultado predeclarado sin modificar retroactivamente la regla de
clasificación de 19A:

- `DEVELOPMENT_RESULT=IMPROVED`
- `WALK_FORWARD_CANDIDATE=YES`

Decisión humana separada (viabilidad absoluta):

- `ABSOLUTE_VIABILITY_GATE=FAIL`
- `DONCHIAN_NET_PNL=-20.008372225067937` → `NET_PNL_POSITIVE=NO`
- `DONCHIAN_PROFIT_FACTOR=0.4222390254700682` → `PROFIT_FACTOR_GT_1=NO`
- `DONCHIAN_EXPECTANCY=-0.04928170498785207` → `EXPECTANCY_POSITIVE=NO`
- Por tanto: `WALK_FORWARD_AUTHORIZED=NO`, `STRATEGY_PROMOTABLE=NO`.

Distinción explícita: `WALK_FORWARD_CANDIDATE=YES` **no** implica
`WALK_FORWARD_AUTHORIZED=YES`. La mejora es relativa a `baseline-v1`; en
términos absolutos la estrategia sigue perdiendo dinero (net PnL negativo,
PF < 1, expectancy negativa).

Diagnósticos señal/ejecución (descriptivos): `DONCHIAN_BUY_SIGNALS=2035`,
`EXECUTED_BUYS=406`, `REJECTED_BUYS=1629`, `DONCHIAN_SELL_SIGNALS=4005`,
`EXECUTED_SELLS=406`, `SELL_SIGNALS_WITHOUT_POSITION=1237`,
`RAW_BREAKOUT_EVENTS=2970`, `BREAKOUTS_CONFIRMED_BY_ADX=2035`,
`BREAKOUTS_BLOCKED_BY_ADX=935`. No se ajustan ADX ni Donchian con estos números.

Disciplina experimental: no se evalúan períodos Donchian alternativos,
thresholds ADX alternativos, Donchian sin ADX, filtros adicionales ni LLM
supervisor en 19B. Sin WALK_FORWARD ni FINAL_HOLDOUT.

## Mensaje de commit propuesto

```text
feat(lab): evaluate ETH Donchian breakout on development (19B)

- compare baseline-v1 vs EthDonchianBreakout-v1 on [0,62208)
- reuse 18B pure helpers; add signal/execution, ADX and trade-structure evidence
- add integration/e2e coverage and full evidence with registry
```

---

**DECISIÓN DEL USUARIO:** ☑ APPROVED → ejecutar commit · 2026-09-13 (HUMAN COMMIT GATE 19B)

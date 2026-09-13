# Commit Candidate Report — 2026-09-13

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> Preparado para el gate humano de la Fase 20B. Nada está staged ni commiteado.

## Objetivo

Evaluación económica DEVELOPMENT de `EthBollingerMeanReversion-v1` (B) contra
`baseline-v1` (A) sobre `[0, 62208)` con runtime-parity real: clasificación
relativa, **Absolute Viability Gate** de Phase 19C y elegibilidad de walk-forward,
más diagnósticos descriptivos de reversión a la media, atribución señal/ejecución
y comprobación del ancla de comportamiento del baseline. Sin walk-forward ni
holdout.

## Rama

| Campo | Valor |
|---|---|
| branch | `feature/phase-08-llm-decision-agent` |
| base commit | `7b608060ac68b3a3ccd85159b869cbc75bdae7a7` (20A committed) |
| staging | none (`git diff --cached --exit-code` PASS) |

## Archivos

- **Creados (tooling):** `harness/scripts/phase20b_development_evaluation.py`
- **Creados (tests):**
  - `tests/integration/test_phase20b_development_evaluation_integration.py`
  - `tests/e2e/test_phase20b_development_evaluation_e2e.py`
- **Creados (evidencia):** `docs/phases/20B/evidence/` (comparison JSON+MD,
  registry de 2 specs y 3 runs, coverage, logs de tests/ruff/format/mypy/
  holdout/protected/staging/WF-denied/strategy-frozen).
- **Modificados / eliminados:** ninguno. No se toca `EthBollingerMeanReversion-v1`,
  `bollinger`, `adx`, `baseline-v1`, `AbsoluteViabilityEvidence`,
  `walk_forward_eligible`, `frozen_dataset` ni artefactos históricos.

## Diff

Todos los archivos 20B son nuevos y no rastreados. `git diff --cached` vacío.

```text
harness/scripts/phase20b_development_evaluation.py             | 672 líneas
tests/integration/test_phase20b_development_evaluation_integration.py | 157 líneas
tests/e2e/test_phase20b_development_evaluation_e2e.py          | 131 líneas
docs/phases/20B/evidence/*                                     | evidencia + registry
```

## Baseline behavior anchor

El baseline no cambió de comportamiento aunque su SpecId sí (el kernel
fingerprint incluye `domain.market.indicators`, ampliado en 20A):

- `BASELINE_IDENTITY_CHANGED=YES`
- `BASELINE_BEHAVIOR_CHANGED=NO`
- Ancla 19B verificada exactamente: trades `406`, net `-20.023553665527754`,
  PF `0.3902907027103561`, expectancy `-0.049319097698344215`, DD
  `0.01677501041581718`.

## Resultado DEVELOPMENT (full `[0, 62208)`)

| Métrica | baseline-v1 | EthBollingerMeanReversion-v1 | Delta |
|---|---|---|---|
| signals_buy | 634 | 460 | -174 |
| signals_sell | 1021 | 32150 | +31129 |
| fills | 812 | 806 | -6 |
| closed_trades | 406 | 403 | -3 |
| net_pnl | -20.023554 | -20.131280 | -0.107727 |
| return_pct | -0.020024 | -0.020131 | -0.000108 |
| fees | 16.242716 | 16.122440 | -0.120276 |
| slippage | 3.248543 | 3.224488 | -0.024055 |
| max_drawdown | 0.016775 | 0.016907 | +0.000132 |
| profit_factor | 0.390291 | 0.285582 | -0.104709 |
| expectancy | -0.049319 | -0.049954 | -0.000634 |
| win_rate | 0.083744 | 0.218362 | +0.134618 |

- **`DEVELOPMENT_RESULT=NOT_IMPROVED`**: expectancy, profit factor y net PnL
  empeoran (≥2 de 3) → no cumple la regla relativa.
- **`ABSOLUTE_VIABILITY_GATE=FAIL`**: `NET_PNL_GT_0=NO`, `EXPECTANCY_GT_0=NO`,
  `PROFIT_FACTOR_GT_1=NO`.
- **`WALK_FORWARD_ELIGIBLE=NO`**, `WALK_FORWARD_AUTHORIZED=NO`.

## Diagnósticos de reversión (descriptivos)

- `RAW_LOWER_BAND_EXCURSIONS=3955`, `REENTRY_EVENTS=1996`,
  `REENTRIES_CONFIRMED_LOW_ADX=470`, `REENTRIES_BLOCKED_BY_ADX=1526`
  (identidad 1996 = 470 + 1526).
- `SIMULTANEOUS_BUY_SELL_SETUPS=10`, `SELL_PRECEDENCE_EVENTS=10`
  (`SELL_PRECEDENCE_EVENTS <= SIMULTANEOUS_BUY_SELL_SETUPS`).
- `BUY_SIGNALS=460 = 470 - 10`; `SELL_SIGNALS=32150`.
- `EXECUTED_BUYS=403`, `REJECTED_BUYS=57`, `SELL_SIGNALS_WITHOUT_POSITION=27936`
  (403 + 57 + 0 = 460).

## Reproducibilidad

`REPRODUCIBILITY=PASS`: mismo `BOLLINGER_SPEC_ID`, distinto `RunId`,
`event_trace_hash` y `metrics_hash` idénticos.

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Lab | 419 passed | `docs/phases/20B/evidence/tests-lab.log` |
| Integration | 49 passed | `docs/phases/20B/evidence/tests-integration.log` |
| E2E | 21 passed | `docs/phases/20B/evidence/tests-e2e.log` |
| Global | 937 passed, 1 skipped | `docs/phases/20B/evidence/coverage-global.log` |

Cubierto: condiciones económicas idénticas, slice DEVELOPMENT completo, ancla de
baseline, SpecIds distintos, métricas deterministas, doble corrida reproducible,
clasificación relativa, integración con `AbsoluteViabilityEvidence` y
`walk_forward_eligible`, contabilidad de diagnósticos, distinción señal/fill,
WALK_FORWARD público denegado, cero lecturas WF, holdout intacto.

## Cobertura

- Global combined statement/branch: `96.27%` (umbral 90% superado).
- Sin módulo Python nuevo de 20B (solo harness/tests), por lo que no aplica el
  requisito de 100% de módulo nuevo.

## Calidad

```bash
uv run ruff check .          # PASS - docs/phases/20B/evidence/ruff.log
uv run ruff format --check . # PASS - docs/phases/20B/evidence/format.log
uv run mypy src tests        # PASS - docs/phases/20B/evidence/mypy.log
uv run pytest --cov=src      # 937 passed, 1 skipped, 96.27% - coverage-global.log
```

## Seguridad / Data safety

- Sin credenciales, tokens ni connection strings; sin `.env`; nada staged.
- `ROUTINE_TEST_REAL_WALK_FORWARD_READS=0`, `PHASE_20B_REAL_WALK_FORWARD_READS=0`.
- No se usa `guarded_walk_forward_open`; acceso público WALK_FORWARD denegado.
- `FINAL_HOLDOUT_READS=0`, `FINAL_HOLDOUT_EXECUTIONS=0`, `HOLDOUT_STATE=PRISTINE`
  (`docs/phases/20B/evidence/holdout-state.log`).
- Runtime protegido intacto (`protected-runtime-diff.log` exit 0).
- Estrategia/indicador congelados (`strategy-frozen.log` exit 0).

## Interpretación

`NOT_IMPROVED` + `ABSOLUTE_VIABILITY_GATE=FAIL` ⇒ la hipótesis de reversión a la
media no supera la referencia relativa ni es viable en términos absolutos en
DEVELOPMENT. No se interpreta como edge: `EDGE_PRESENT` y `STRATEGY_PROMOTABLE`
permanecen `NOT_EVALUATED`; el walk-forward seguiría siendo necesario para
evidencia OOS y no está autorizado.

## Disciplina experimental

No se evaluaron alternativas de periodo Bollinger, multiplicador, umbral ADX,
RSI, BTC, LLM, multi-timeframe ni variaciones de stop/salida. Sin segundo
candidato de reversión en 20B.

## Riesgos

- DEVELOPMENT no demuestra edge out-of-sample.
- El baseline cambió de SpecId por el kernel fingerprint (indicators ampliado);
  el comportamiento económico se verificó idéntico.

## Deuda técnica

- Sin deuda funcional nueva. El script 20B duplica helpers de formato
  JSON/Markdown de 19B (deliberado para no refactorizar artefactos históricos).

## Interpretación humana (2026-09-13)

`DEVELOPMENT_RESULT=NOT_IMPROVED` (no reinterpretar):

- `BASELINE_NET_PNL=-20.023553665527754` → `BOLLINGER_NET_PNL=-20.13128034069649`
- `BASELINE_PROFIT_FACTOR=0.3902907027103561` → `BOLLINGER_PROFIT_FACTOR=0.2855818256351072`
- `BASELINE_EXPECTANCY=-0.049319097698344215` → `BOLLINGER_EXPECTANCY=-0.0499535492324975`
- `BASELINE_MAX_DRAWDOWN=0.01677501041581718` → `BOLLINGER_MAX_DRAWDOWN=0.016906792313621962`
- `BASELINE_WIN_RATE=0.08374384236453201` → `BOLLINGER_WIN_RATE=0.21836228287841192`

La win rate mejora materialmente, pero net PnL, profit factor y expectancy
empeoran y el drawdown empeora ligeramente. Una win rate más alta **no**
representa mejor calidad económica aquí.

Viability (Phase 19C): `NET_PNL_GT_0=NO`, `EXPECTANCY_GT_0=NO`,
`PROFIT_FACTOR_GT_1=NO` ⇒ `ABSOLUTE_VIABILITY_GATE=FAIL`,
`WALK_FORWARD_ELIGIBLE=NO`, `WALK_FORWARD_AUTHORIZED=NO`,
`STRATEGY_PROMOTABLE=NO`.

Baseline: `BASELINE_IDENTITY_CHANGED=YES`, `BASELINE_BEHAVIOR_CHANGED=NO`
(el fingerprint de kernel/fuente cambió porque `domain.market.indicators` ganó
funcionalidad aprobada, mientras el ancla de comportamiento DEVELOPMENT quedó
exactamente igual). No se altera el mecanismo de identidad.

Diagnósticos preservados como descriptivos: `RAW_LOWER_BAND_EXCURSIONS=3955`,
`REENTRY_EVENTS=1996`, `REENTRIES_CONFIRMED_LOW_ADX=470`,
`REENTRIES_BLOCKED_BY_ADX=1526`, `BUY_SIGNALS=460`, `SELL_SIGNALS=32150`,
`EXECUTED_BUYS=403`, `EXECUTED_SELLS=403`, `REJECTED_BUYS=57`,
`SELL_SIGNALS_WITHOUT_POSITION=27936`, `SIMULTANEOUS_BUY_SELL_SETUPS=10`,
`SELL_PRECEDENCE_EVENTS=10`. No se ajustan periodo Bollinger, multiplicador,
`ADX_MAX`, entrada ni salida con estos resultados.

Disciplina: `EthBollingerMeanReversion-v1` queda completa con
`NOT_IMPROVED`; no se crean variantes dentro de 20B.

## Mensaje de commit propuesto

```text
feat(lab): evaluate Bollinger mean reversion on development (20B)

- compare baseline-v1 vs EthBollingerMeanReversion-v1 on [0,62208)
- compute relative classification, 19C absolute viability and WF eligibility
- add mean-reversion diagnostics, baseline anchor check and full evidence
```

---

**DECISIÓN DEL USUARIO:** ☑ APPROVED → ejecutar commit · 2026-09-13 (HUMAN COMMIT GATE 20B)

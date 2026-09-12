# Commit Candidate Report — 2026-09-12

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> Preparado para el gate de implementación 18C. Nada está staged ni commiteado.

## Objetivo

Implementar `EmaRsiBtcRegime-v1`: un candidato Strategy Lab que preserva
`baseline-v1` ETH y filtra únicamente los BUY con un régimen BTC causal de
tendencia + pendiente:

```
BTC_RISK_ON[t] = EMA20[t] > EMA50[t] AND EMA20[t] > EMA20[t-4]
```

con `btc_slope_lookback = 4`. La segunda comparación es pendiente/dirección
positiva de la EMA, no aceleración cuantitativa.

## Rama

| Campo | Valor |
|---|---|
| branch | `feature/phase-08-llm-decision-agent` |
| base commit | `6743a79` (18B committed) |
| staging | none (`git diff --cached --exit-code` PASS) |

## Archivos

- **Creados (diseño/plan):**
  - `docs/superpowers/specs/2026-09-12-btc-regime-v1-design.md`
  - `docs/superpowers/plans/2026-09-12-btc-regime-v1.md`
- **Creados (código/tooling):**
  - `src/lab/strategies/ema_rsi_btc_regime.py` (84 statements)
  - `harness/scripts/phase18c_development_smoke.py`
- **Creados (tests):**
  - `tests/lab/test_ema_rsi_btc_regime.py`
  - `tests/lab/test_phase18c_development_smoke.py`
  - `tests/integration/test_ema_rsi_btc_regime_integration.py`
  - `tests/e2e/test_ema_rsi_btc_regime_e2e.py`
- **Creados (evidencia):** `docs/phases/18C/evidence/` (smoke JSON, coverage
  JSON, logs de tests/ruff/format/mypy/holdout/staging).
- **Modificados / eliminados:** ninguno.

## Diff

Todos los archivos 18C son nuevos y no rastreados. No hay cambios sobre archivos
de producto existentes ni sobre runtime protegido; `git diff --cached` vacío.

```text
src/lab/strategies/ema_rsi_btc_regime.py                  | 186 líneas
harness/scripts/phase18c_development_smoke.py             | 112 líneas
tests/lab/test_ema_rsi_btc_regime.py                      | 291 líneas
tests/lab/test_phase18c_development_smoke.py              |  33 líneas
tests/integration/test_ema_rsi_btc_regime_integration.py  | 159 líneas
tests/e2e/test_ema_rsi_btc_regime_e2e.py                  | 155 líneas
docs/superpowers/specs/2026-09-12-btc-regime-v1-design.md | 263 líneas
docs/superpowers/plans/2026-09-12-btc-regime-v1.md        | 351 líneas
docs/phases/18C/evidence/*                                | evidencia
```

## Arquitectura afectada

Un módulo lab nuevo (`lab.strategies.ema_rsi_btc_regime`) compone
`EmaRsiBaseline` (sin modificarlo) y precomputa `BTC_RISK_ON` con
`domain.market.indicators.ema`. Reutiliza `StrategyDefinition`/
`strategy_artifact_identity` y el mapping `ExperimentSpec` `primary`/`context`.
No modifica `EmaRsiBaseline`, `EmaRsiBtcContext-v1`, `LabSessionRunner` ni el
runtime protegido.

Blast radius (`check_index_coverage`, generación `2026-09-12T21:11:44Z`): módulo,
script, tests, diseño y plan sin issues registrados. El cambio solo **consume**
símbolos existentes; cero símbolos de producto modificados.

## Índice del grafo

- [x] Índice refrescado tras la implementación (`nodes=…`, generación
      `2026-09-12T21:11:44Z`).
- [x] `check_index_coverage` sin issues sobre los archivos 18C.
- [ ] Re-index post-commit: pendiente tras autorización.

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Lab | 326 passed | `docs/phases/18C/evidence/tests-lab.log` |
| Integration | 35 passed | `docs/phases/18C/evidence/tests-integration.log` |
| E2E | 8 passed | `docs/phases/18C/evidence/tests-e2e.log` |
| Global | 794 passed, 1 skipped | `docs/phases/18C/evidence/coverage-global.log` |
| 18C focused | 39 passed | `docs/phases/18C/evidence/coverage-18c.log` |

## Cobertura

- Global combined statement/branch: `96.08%` (umbral 90% superado).
- Módulo nuevo `src/lab/strategies/ema_rsi_btc_regime.py`: statements `84/84`
  (`100%`), branches `32/32` (`100%`).
- Evidencia: `docs/phases/18C/evidence/coverage.json` y `coverage-18c.json`.

## Calidad

```bash
uv run ruff check .          # PASS - docs/phases/18C/evidence/ruff.log
uv run ruff format --check . # PASS - docs/phases/18C/evidence/format.log
uv run mypy src tests        # PASS - docs/phases/18C/evidence/mypy.log
uv run pytest --cov=src      # 794 passed, 1 skipped, 96.08% - coverage-global.log
```

## Smoke DEVELOPMENT (no económico)

- Rango `[0, 5000)` ETHUSDT + BTCUSDT 15m, unidad = decisiones de estrategia.
- Baseline BUY: `58`; regime BUY: `35`; BUY bloqueados: `23` (identidad
  58 = 35 + 23).
- `FINAL_HOLDOUT_READS=0`, `FINAL_HOLDOUT_EXECUTIONS=0`.
- Evidencia: `docs/phases/18C/evidence/development-smoke.json`.
- Sin evaluación económica, sin walk-forward, sin holdout.

## Seguridad

- [x] Sin credenciales, tokens, claves ni connection strings.
- [x] Sin `.env` ni certificados; secret scan limpio.
- [x] Nada staged (`docs/phases/18C/evidence/no-staging.log`).

## Data safety

- `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0`, `FINAL_HOLDOUT_EXECUTIONS=0`.
- `HOLDOUT_STATE=PRISTINE` (`docs/phases/18C/evidence/holdout-state.log`).
- Runtime protegido intacto (`protected-runtime-diff.log` exit 0).

## Riesgos

- Este commit **no** incluye evaluación económica: `EDGE_PRESENT` y
  `STRATEGY_PROMOTABLE` permanecen `NOT_EVALUATED`.
- La regla añade una condición de pendiente; su valor económico se medirá en una
  fase posterior contra `baseline-v1` (PRIMARY) y contra `EmaRsiBtcContext-v1`
  (incremental), sin ajustar parámetros tras observar resultados.

## Deuda técnica

- Sin deuda funcional nueva. La evaluación económica DEVELOPMENT de
  `EmaRsiBtcRegime-v1` queda explícitamente fuera de esta fase de implementación.

## Mensaje de commit propuesto

```text
feat(lab): add EmaRsiBtcRegime BTC trend+slope candidate (18C)

- compose frozen baseline-v1 ETH with causal BTC EMA trend+slope BUY gate
- add DEVELOPMENT smoke, alignment/identity tests and no-lookahead coverage
- reuse StrategyArtifactIdentity and ExperimentSpec primary/context
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

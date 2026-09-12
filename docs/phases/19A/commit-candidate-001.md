# Commit Candidate Report — 2026-09-12

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> Preparado para el gate de implementación 19A. Nada está staged ni commiteado.

## Objetivo

Implementar `EthDonchianBreakout-v1`: estrategia ETH 15m standalone de ruptura
Donchian por cierre, con gate de fuerza de tendencia mediante un ADX de Wilder
causal nuevo. TDD, sin evaluación económica, sin BTC y sin LLM.

Regla congelada:

```
BUY : close[t] > max(high[t-20:t]) AND adx14[t] > 20
SELL: close[t] < min(low[t-10:t])
```

Vela actual estrictamente excluida de ambas ventanas; desigualdades estrictas.
ADX afecta solo al BUY; el SELL es independiente del ADX.

## Rama

| Campo | Valor |
|---|---|
| branch | `feature/phase-08-llm-decision-agent` |
| base commit | `75c353c9e05ecc55d8913ef2b2e2c3a3064cf92c` (18D committed) |
| staging | none (`git diff --cached --exit-code` PASS) |

## Archivos

- **Modificados (solo ADX aprobado):**
  - `src/domain/market/indicators.py` (+64 líneas: `adx`)
  - `tests/test_indicators.py` (+59 líneas: tests ADX)
- **Creados (diseño/plan):**
  - `docs/superpowers/specs/2026-09-12-eth-donchian-breakout-v1-design.md`
  - `docs/superpowers/plans/2026-09-12-eth-donchian-breakout-v1.md`
- **Creados (código/tooling):**
  - `src/lab/strategies/eth_donchian_breakout.py`
  - `harness/scripts/phase19a_development_smoke.py`
- **Creados (tests):**
  - `tests/lab/test_eth_donchian_breakout.py`
  - `tests/lab/test_phase19a_development_smoke.py`
  - `tests/integration/test_eth_donchian_breakout_integration.py`
  - `tests/e2e/test_eth_donchian_breakout_e2e.py`
- **Creados (evidencia):** `docs/phases/19A/evidence/`.
- **Eliminados:** ninguno.

Ningún otro archivo se modifica. Las estrategias históricas (`baseline-v1`,
`EmaRsiBtcContext-v1`, `EmaRsiBtcRegime-v1`) y el runtime protegido quedan
intactos.

## Diff

```text
src/domain/market/indicators.py          | +64 (adx)
tests/test_indicators.py                 | +59 (ADX tests)
src/lab/strategies/eth_donchian_breakout.py | 135 líneas
harness/scripts/phase19a_development_smoke.py | 99 líneas
tests/lab/test_eth_donchian_breakout.py  | 245 líneas
tests/lab/test_phase19a_development_smoke.py | 30 líneas
tests/integration/test_eth_donchian_breakout_integration.py | 60 líneas
tests/e2e/test_eth_donchian_breakout_e2e.py | 126 líneas
docs/superpowers/{specs,plans}/2026-09-12-eth-donchian-breakout-v1*.md
docs/phases/19A/evidence/*
```

## Arquitectura afectada

- `domain.market.indicators` gana `adx(candles, period)` (Wilder, causal,
  `FIRST_ADX_INDEX = 2n-1`; 27 para n=14). Es la única modificación permitida
  fuera de `src/lab` y tests.
- `src/lab/strategies/eth_donchian_breakout.py`: estrategia standalone que
  implementa el protocolo `Strategy`; no compone `EmaRsiBaseline` ni ninguna
  estrategia histórica.
- Reutiliza `StrategyDefinition`, `strategy_artifact_identity`,
  `ExperimentSpec`, `FrozenDatasetAdapter`, `LabSessionRunner`, `RiskEngine` y
  `PaperEngine`. Sin framework nuevo.
- `check_index_coverage` (generación `2026-09-12T22:12:04Z`): sin issues sobre
  los archivos 19A.

## Índice del grafo

- [x] Índice refrescado tras la implementación.
- [x] `check_index_coverage` sin issues sobre los archivos 19A.
- [ ] Re-index post-commit: pendiente tras autorización.

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Lab | 351 passed | `docs/phases/19A/evidence/tests-lab.log` |
| Integration | 40 passed | `docs/phases/19A/evidence/tests-integration.log` |
| E2E | 13 passed | `docs/phases/19A/evidence/tests-e2e.log` |
| Global | 838 passed, 1 skipped | `docs/phases/19A/evidence/coverage-global.log` |

Cobertura funcional: ADX first index 27, ventanas Donchian con exclusión de la
vela actual, límites estrictos, gate ADX, SELL independiente del ADX, warmup,
corrupción temporal (no-lookahead), determinismo, identidad por parámetro,
`SpecId`, holdout denegado, integración con `LabSessionRunner` y e2e
DEVELOPMENT-only.

## Cobertura

- Global combined statement/branch: `96.17%` (umbral 90% superado).
- `domain.market.indicators` (incluye `adx`): `100%` statements y branches.
- Módulo nuevo `src/lab/strategies/eth_donchian_breakout.py`: statements `65/65`
  (`100%`), branches `20/20` (`100%`).
- Evidencia: `docs/phases/19A/evidence/coverage.json` y `coverage-19a.json`.

## Calidad

```bash
uv run ruff check .          # PASS - docs/phases/19A/evidence/ruff.log
uv run ruff format --check . # PASS - docs/phases/19A/evidence/format.log
uv run mypy src tests        # PASS - docs/phases/19A/evidence/mypy.log
uv run pytest --cov=src      # 838 passed, 1 skipped, 96.17% - coverage-global.log
```

## Smoke DEVELOPMENT (no económico)

- Rango `[0, 5000)` ETHUSDT 15m, unidad = decisiones de estrategia.
- BUY `150`, SELL `285`, HOLD `4565`; `FIRST_ADX_INDEX=27`.
- `FINAL_HOLDOUT_READS=0`, `FINAL_HOLDOUT_EXECUTIONS=0`.
- Evidencia: `docs/phases/19A/evidence/development-smoke.log`.
- Sin PnL, sin walk-forward, sin holdout.

## Seguridad

- [x] Sin credenciales, tokens, claves ni connection strings.
- [x] Sin `.env` ni certificados.
- [x] Nada staged (`docs/phases/19A/evidence/no-staging.log`).

## Data safety

- `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0`, `FINAL_HOLDOUT_EXECUTIONS=0`.
- `HOLDOUT_STATE=PRISTINE` (`docs/phases/19A/evidence/holdout-state.log`).
- Runtime protegido intacto (`protected-runtime-diff.log` exit 0).

## Riesgos

- Esta fase no incluye evaluación económica: `EDGE_PRESENT` y
  `STRATEGY_PROMOTABLE` permanecen `NOT_EVALUATED`.
- `adx` es una adición a un módulo de dominio compartido; cubierta al 100% y sin
  cambiar funciones existentes.
- La estrategia es standalone; no se compara con `baseline-v1` todavía.

## Deuda técnica

- Sin deuda funcional nueva. La evaluación económica DEVELOPMENT de
  `EthDonchianBreakout-v1` queda explícitamente fuera de esta fase.

## Mensaje de commit propuesto

```text
feat(lab): add Donchian breakout strategy with causal ADX (19A)

- add causal Wilder adx (first index 2n-1) to domain.market.indicators
- add standalone EthDonchianBreakout-v1 with current-candle-excluded windows
- add DEVELOPMENT smoke, unit/integration/e2e tests and full evidence
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

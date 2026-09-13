# Commit Candidate Report — 2026-09-13

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> Preparado para el gate de implementación 20A. Nada está staged ni commiteado.

## Objetivo

Implementar `EthBollingerMeanReversion-v1`: estrategia ETH 15m standalone de
reversión a la media, con entrada por excursión + re-entrada en la banda de
Bollinger y filtro de régimen ADX bajo, más la adición causal mínima del
indicador `bollinger` en `domain.market.indicators`. TDD, sin evaluación
económica, sin BTC y sin LLM.

## Rama

| Campo | Valor |
|---|---|
| branch | `feature/phase-08-llm-decision-agent` |
| base commit | `e521687953a4d1022b06f5b86af91ede838ac959` (19C committed) |
| staging | none (`git diff --cached --exit-code` PASS) |

## Archivos

- **Modificados (dominio aprobado):**
  - `src/domain/market/indicators.py` (+35: `BollingerBands`, `bollinger`)
  - `tests/test_indicators.py` (+74: tests Bollinger)
- **Creados (diseño/plan):**
  - `docs/superpowers/specs/2026-09-12-eth-bollinger-mean-reversion-v1-design.md`
  - `docs/superpowers/plans/2026-09-12-eth-bollinger-mean-reversion-v1.md`
- **Creados (código/tooling):**
  - `src/lab/strategies/eth_bollinger_mean_reversion.py`
  - `harness/scripts/phase20a_development_smoke.py`
- **Creados (tests):**
  - `tests/lab/test_eth_bollinger_mean_reversion.py`
  - `tests/lab/test_phase20a_development_smoke.py`
  - `tests/integration/test_eth_bollinger_mean_reversion_integration.py`
  - `tests/e2e/test_eth_bollinger_mean_reversion_e2e.py`
- **Creados (evidencia):** `docs/phases/20A/evidence/`.
- **Eliminados:** ninguno.

No se modifica ninguna estrategia histórica, `adx`, ni el runtime protegido.

## Contrato Bollinger

`bollinger(values, period=20, multiplier=2.0) -> list[BollingerBands | None]`:
media y desviación poblacional (`statistics.pstdev`, `ddof=0`), incluye el cierre
confirmado actual, primer índice disponible `19`, causal. Sin numpy/pandas.
`multiplier` debe ser finito y `> 0`.

## Reglas congeladas

- Parámetros: `bollinger_period=20`, `bollinger_stddev_multiplier=2.0`,
  `adx_period=14`, `adx_max=20.0`.
- Orden: (1) `close[t] >= MIDDLE[t]` → SELL; (2) si no, `close[t-1] < LOWER[t-1]`
  (estricto) AND `close[t] >= LOWER[t]` (inclusivo) AND `ADX[t] < 20.0`
  (estricto) → BUY; (3) HOLD.
- SELL precede a BUY y es independiente del ADX; sin warmup global de ADX.
- Warmup: Bollinger desde índice 19; BUY efectivo desde ADX listo (27); SELL
  desde 19.

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Lab | 419 passed | `docs/phases/20A/evidence/tests-lab.log` |
| Integration | 45 passed | `docs/phases/20A/evidence/tests-integration.log` |
| E2E | 18 passed | `docs/phases/20A/evidence/tests-e2e.log` |
| Global | 930 passed, 1 skipped | `docs/phases/20A/evidence/coverage-global.log` |

Cubierto: Bollinger (primer índice 19, `ddof=0`, valores exactos, flat, causal,
mutación futura, determinismo, periodo/multiplicador inválidos); estrategia
(BUY, límites estricto/inclusivo, gate ADX `<20`/`==20`/`>20`/ausente, SELL y
`==` middle, SELL independiente de ADX, precedencia SELL, warmup, no-lookahead,
determinismo, identidad por parámetro, `SpecId`, holdout denegado); integración
runtime-parity y e2e DEVELOPMENT-only.

## Cobertura

- Global combined statement/branch: `96.27%` (umbral 90% superado).
- `src/lab/strategies/eth_bollinger_mean_reversion.py`: statements `55/55`,
  branches `16/16` (`100%`).
- `domain.market.indicators` (incluye `bollinger`): `100%` (211 statements,
  70 branches).
- Evidencia: `docs/phases/20A/evidence/coverage.json` y `coverage-20a.json`.

## Calidad

```bash
uv run ruff check .          # PASS - docs/phases/20A/evidence/ruff.log
uv run ruff format --check . # PASS - docs/phases/20A/evidence/format.log
uv run mypy src tests        # PASS - docs/phases/20A/evidence/mypy.log
uv run pytest --cov=src      # 930 passed, 1 skipped, 96.27% - coverage-global.log
```

## Smoke DEVELOPMENT (no económico)

- Rango `[0, 5000)` ETHUSDT 15m, unidad = decisiones de estrategia.
- BUY `31`, SELL `2545`, HOLD `2424`; `BOLLINGER_FIRST_INDEX=19`,
  `ADX_FIRST_INDEX=27`.
- `FINAL_HOLDOUT_READS=0`, `FINAL_HOLDOUT_EXECUTIONS=0`.
- Evidencia: `docs/phases/20A/evidence/development-smoke.log`.
- Sin PnL, sin walk-forward, sin holdout.

## Seguridad / Data safety

- Sin credenciales, tokens ni connection strings; sin `.env`; nada staged.
- `ROUTINE_TEST_REAL_WALK_FORWARD_READS=0`, `PHASE_20A_REAL_WALK_FORWARD_READS=0`.
- No se usa `guarded_walk_forward_open`; acceso público WALK_FORWARD sigue
  denegado.
- `FINAL_HOLDOUT_READS=0`, `FINAL_HOLDOUT_EXECUTIONS=0`, `HOLDOUT_STATE=PRISTINE`
  (`docs/phases/20A/evidence/holdout-state.log`).
- Runtime protegido intacto (`protected-runtime-diff.log` exit 0).

## Riesgos

- Sin evaluación económica: `EDGE_PRESENT=NOT_EVALUATED`,
  `ABSOLUTE_VIABILITY_GATE=NOT_EVALUATED`, `STRATEGY_PROMOTABLE=NOT_EVALUATED`.
- `bollinger` es una adición a un módulo de dominio compartido; cubierta al
  100% y sin cambiar funciones existentes.

## Deuda técnica

- Sin deuda funcional nueva. La evaluación económica DEVELOPMENT de
  `EthBollingerMeanReversion-v1` queda explícitamente fuera de esta fase.

## Mensaje de commit propuesto

```text
feat(lab): add ETH Bollinger mean-reversion candidate (20A)

- add causal bollinger indicator (population stddev, first index period-1)
- add standalone EthBollingerMeanReversion-v1 with SELL-over-BUY precedence
- add DEVELOPMENT smoke, unit/integration/e2e tests and full evidence
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

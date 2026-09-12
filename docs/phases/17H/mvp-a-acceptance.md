# MVP-A Acceptance Report — Strategy Lab (Fase 17H)

> Cierre de MVP-A. Sin features nuevas, sin MVP-B, sin Mode 3, sin holdout.
> UAT_STATUS=PASS (10/10, ver `uat.md`).

## Experiment identity

`ExperimentSpec` / `ExperimentRun` / `spec_id` determinista (17A).
Toda ejecución ligada a su SpecId; `application_git_sha` es provenance,
no identidad semántica.

## Strategy / kernel identity

`StrategyArtifactIdentity` + `KernelIdentity` + `ImplementationFingerprint`
(17B). E2E usa identidades reales (importlib) con el mismo SpecId que 17F.

## Frozen datasets

`BYBIT_ETHBTC_V001`, ETHUSDT 15m, 103680 filas, SHA-256 verificados contra
el manifest. `FrozenDatasetAdapter`: timestamps/OHLCV exactos, sin mutar,
sin resamplear, sin sintéticos (17D).

## Split v1

DEVELOPMENT [0,62208) · WALK_FORWARD [62208,88128) ·
FINAL_HOLDOUT [88128,103680). Temporal, contiguo, day-aligned (17C-A/B).

## Holdout safety

FINAL_HOLDOUT_READS=0 · FINAL_HOLDOUT_EXECUTIONS=0 ·
HOLDOUT_STATE=PRISTINE. Acceso bloqueado por guard (E2E + UAT-09).

## Runtime parity

LabSessionRunner = misma secuencia que `PaperRunner.handle_kline`
(precio=close, atr=None, confidence=1.0, MEDIUM) con Strategy + RiskEngine +
PaperEngine reales. Paridad cruzada verificada por vela con anclas
calculadas a mano (17D).

## Registry

Filesystem `<spec_id>/spec.json + runs/<run_id>.json`, idempotente ante
igualdad, fail-closed ante conflicto/manipulación (17E).

## Double-run reproducibility

Mismo spec → mismos `event_trace_hash`/`metrics_hash`, RunIds distintos;
E2E lo re-verifica incluyendo igualdad del resultado de promoción (17E/17H).

## Walk-forward

3 ventanas (8640 filas): nets -3.08/-7.02/-5.97, agregado -16.07 (-1.61%),
253 trades, PF 0.0, expectancy -0.064. 0/3 rentables (17F).

## Robustness

7 variantes 1-a-1 en DEVELOPMENT completo: rango [-20.09,-20.02],
STABLE=YES = negativo-estable, sin selección ni promoción (17F).

## Promotion gates

Máquina MVP-A por evidencia (17G): baseline DRAFT → PARITY_PASSED →
ROBUSTNESS_PASSED REJECTED (`NEGATIVE_WALK_FORWARD: STABLE_NEGATIVE`) →
HOLDOUT_READY=NO. Estados post-MVP-A bloqueados explícitamente.

## Integration tests

15 passed con PostgreSQL (incluye deuda pgvector saldada pre-17E).

## E2E

`tests/e2e/test_strategy_lab_e2e.py`: cadena completa + double-run +
failure path, todo PASS (17H).

## UAT status

UAT_STATUS=PASS · UAT_PASSED=10 · UAT_FAILED=0 · HUMAN_APPROVED=YES.
10 casos ejecutados con veredicto humano explícito (ver `uat.md`).

MVP_A_TECHNICAL_ACCEPTANCE=PASS
MVP_A_UAT=PASS

## Veredicto baseline

BASELINE_EDGE_PRESENT=NO
BASELINE_PROMOTABLE=NO
BASELINE_HOLDOUT_READY=NO

Esto NO es fallo de MVP-A: el Lab rechazó correctamente una estrategia
sin edge demostrado. MVP-A termina como máximo en HOLDOUT_READY, solo para
estrategias que cumplan los requisitos.

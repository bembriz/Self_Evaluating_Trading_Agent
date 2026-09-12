# Commit Candidate Report - 2026-09-12

> Prepared for the Phase 18A human gate. Selective staging and commit were approved
> explicitly by the user on 2026-09-12; push remains unauthorized.

## Objetivo

Add `EmaRsiBtcContext-v1`, a Strategy Lab candidate that preserves the exact ETH
`EmaRsiBaseline` signal path and applies only a causal `BTC EMA20 > EMA50` gate to
candidate BUY decisions.

## Rama

| Campo | Valor |
|---|---|
| branch | `feature/phase-08-llm-decision-agent` |
| base commit | `f6899b53bb5c9dfb459148e0930bd6e420bf6f10` |
| staging | approved for the 47-file Phase 18A scope only |

## Archivos

Created production/tooling:

- `src/lab/strategies/__init__.py`
- `src/lab/strategies/ema_rsi_btc_context.py`
- `harness/scripts/phase18a_development_smoke.py`

Created tests:

- `tests/lab/test_ema_rsi_btc_context.py`
- `tests/lab/test_phase18a_development_smoke.py`
- `tests/integration/test_ema_rsi_btc_context_integration.py`
- `tests/e2e/test_ema_rsi_btc_context_e2e.py`

Created design and plan:

- `docs/superpowers/specs/2026-09-12-ema-rsi-btc-context-v1-design.md`
- `docs/superpowers/plans/2026-09-12-ema-rsi-btc-context-v1.md`

Created evidence:

- `docs/phases/18A/evidence/` (definitions, alignment, smoke JSON, review, graph impact,
  immutable command logs, and coverage JSON)
- `docs/phases/18A/commit-candidate-001.md`

Modified existing product/runtime files: none.

## Diff

All Phase 18A files were new and untracked when this report was prepared. The user then
approved selective staging and commit of the verified 47-file scope. The shared checkout
also contains unrelated pre-existing dirty paths; they remain untouched.

Protected runtime diff against HEAD is empty. Evidence:
`docs/phases/18A/evidence/protected-runtime-diff.log`.

## Arquitectura afectada

One new Strategy Lab candidate module composes existing domain/lab contracts:

- `domain.trading.strategy.EmaRsiBaseline`
- `domain.market.indicators.ema`
- `lab.frozen_dataset.FrozenDatasetAdapter`
- `lab.fingerprints.StrategyDefinition`
- `lab.experiment_spec.ExperimentSpec`
- `lab.session_runner.LabSessionRunner`

No existing production symbol was modified. Indexed candidate callers are limited to new
tests and the Phase 18A smoke script. See
`docs/phases/18A/evidence/graph-impact.md`.

## Indice del grafo

- [x] Watcher refreshed the worktree index after implementation and review fixes.
- [x] Exact coverage checked for Phase 18A code, tests, plan, design, and key evidence.
- [ ] Post-commit reindex: not applicable because commit is prohibited/not performed.

The bounded change touches one new production module and has zero external certified
runtime callers. `detect_changes` is polluted by unrelated dirty worktree paths; exact
candidate traces are used for the scoped conclusion.

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Lab | 282 passed | `docs/phases/18A/evidence/tests-lab-r2.log` |
| Integration | 23 passed | `docs/phases/18A/evidence/tests-integration-r3.log` |
| E2E | 3 passed | `docs/phases/18A/evidence/tests-e2e-r2.log` |
| Phase 18A focused | 34 passed | `docs/phases/18A/evidence/coverage-18a-r3.log` |
| Global | 733 passed, 1 skipped | `docs/phases/18A/evidence/coverage-global-r3.log` |

The sole warning is an existing Starlette/httpx deprecation warning unrelated to Phase
18A.

## Cobertura

- Global combined statement/branch coverage: `95.93%`.
- Global statements: `4739/4903` covered.
- Global branches: `820/892` covered.
- New candidate statements: `71/71` (`100%`).
- New candidate branches: `26/26` (`100%`).
- Evidence: `docs/phases/18A/evidence/coverage.json` and
  `docs/phases/18A/evidence/coverage-18a.json`.

## Calidad

```text
ruff check .             PASS - docs/phases/18A/evidence/ruff-r3.log
ruff format --check .    PASS - docs/phases/18A/evidence/format-r4.log
mypy src tests           PASS - docs/phases/18A/evidence/mypy-r3.log
pytest global + coverage PASS - docs/phases/18A/evidence/coverage-global-r3.log
```

## Seguridad

- [x] No credentials, tokens, keys, passwords, or connection strings in Phase 18A files.
- [x] No `.env`, certificate, or key file included.
- [x] Selective staging authorized for Phase 18A files only.

## Development Smoke

- Range: DEVELOPMENT `[0, 5000)` for ETHUSDT and BTCUSDT 15m.
- Counter unit: strategy decisions, not fills/orders.
- Baseline BUY signals: `58`.
- BTC-context BUY signals: `37`.
- BTC-blocked BUYs: `21`.
- Timestamp alignment: PASS.
- Edge/promotability: NOT_EVALUATED.
- Evidence: `docs/phases/18A/evidence/development-smoke-r2.log`.

## Holdout

- Observed requested ranges: ETH `[0,5000)`, BTC `[0,5000)`.
- FINAL_HOLDOUT range requests: `0`.
- FINAL_HOLDOUT executions: `0`.
- Holdout state: `PRISTINE`.
- Walk-forward executions: `0`.

## Riesgos

- BTC context is precomputed in memory; causality is guaranteed by the existing causal EMA
  implementation and temporal-corruption tests, not by incremental runtime calculation.
- Holdout telemetry is request-level within Phase 18A wrappers, not process-wide file I/O
  instrumentation. Every observed adapter request is DEVELOPMENT-only.
- This phase provides no evidence of economic edge or promotability.

## Deuda tecnica

No new framework or known functional debt. Formal walk-forward/economic evaluation remains
explicitly outside Phase 18A.

## Mensaje de commit propuesto

```text
feat(lab): add BTC context gate candidate

- compose baseline ETH signals with causal aligned BTC EMA context
- add DEVELOPMENT smoke, deterministic identity, and complete gate evidence
```

## Decision

`COMMIT_CANDIDATE_READY=YES`. The user explicitly authorized selective staging of the 47
verified Phase 18A files and creation of the proposed commit. No push was authorized.

**DECISION DEL USUARIO:** APPROVED for Phase 18A staging and commit on 2026-09-12.

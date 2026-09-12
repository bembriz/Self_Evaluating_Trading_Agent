# Phase 18A Graph Impact

## Index

- Project: `home-xuum-Documentos-proyectos-Self-Evaluating_Trading_Agent`
- HEAD: `f6899b53bb5c9dfb459148e0930bd6e420bf6f10`
- Latest observed generation: `2026-09-12T19:03:13Z`
- Status: `ready`
- Phase 18A exact paths: no recorded coverage issue
- Scope gaps: ignored `__pycache__` directories only

Coverage is a best-effort index signal, not proof of source completeness. Exact source and
test files were also read or executed directly.

## Bounded Phase 18A Impact

`EmaRsiBtcContext.on_candle` has 17 reachable callers within depth 3. They are limited to
the new Phase 18A lab tests, E2E test, and development smoke script. Its direct production
dependency is the unchanged `EmaRsiBaseline.on_candle`; it also constructs existing
`Signal` values for confirmed/blocked BUYs.

`EmaRsiBtcContext.from_adapters` has six indexed callers, all in the new integration/E2E
paths. It consumes the existing `FrozenDatasetAdapter` contract. The candidate additionally
reuses the existing EMA indicator, Phase 17B `StrategyDefinition` identity contract,
`ExperimentSpec`, and unchanged `LabSessionRunner`.

The Phase 18A change introduces one production module under `src/lab/strategies`; it adds
no caller from certified runtime and changes no existing production symbol.

## Detect Changes Limitation

`detect_changes(since=HEAD)` sees every pre-existing dirty/untracked path in the shared
checkout and reports 57 impacted symbols across `src/lab`, `src/domain`, and
`src/application`. That aggregate is not a valid Phase 18A-only blast radius. The bounded
traces above isolate the candidate symbols and paths; unrelated dirty files were neither
modified nor included in this report's Phase 18A impact conclusion.

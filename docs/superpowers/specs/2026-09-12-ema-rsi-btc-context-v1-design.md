# EmaRsiBtcContext-v1 Design

## Goal

Implement Phase 18A as one controlled Strategy Lab candidate that preserves
`baseline-v1` ETH behavior and adds only a causal BTC trend gate to candidate
BUY signals.

## Scope

- Strategy name: `EmaRsiBtcContext`.
- Strategy version: `ema-rsi-btc-context-v1`.
- Primary asset: `ETHUSDT` 15m.
- Context asset: `BTCUSDT` 15m.
- Frozen dataset: `BYBIT_ETHBTC_V001`.
- Allowed execution data: DEVELOPMENT `[0, 62208)` only.
- No LLM, ML, walk-forward evaluation, holdout access, or performance claim.

## Architecture

Add `src/lab/strategies/ema_rsi_btc_context.py` outside the certified runtime.
The module contains a frozen configuration, the candidate strategy, alignment
validation, causal BTC EMA context calculation, and the existing
`StrategyDefinition` declaration needed for artifact identity. It introduces
no framework, registry, factory, plugin system, or new fingerprinting layer.

`EmaRsiBtcContext` composes a fresh `EmaRsiBaseline` instance rather than
reimplementing ETH EMA/RSI behavior. It receives the aligned primary ETH and
context BTC candles before execution. Construction fails closed unless both
sequences have the same non-zero length and every timestamp matches at the
same index. The adapters used by real executions also prove the same dataset,
timeframe, and row slice before strategy construction.

`LabSessionRunner` remains unchanged and continues iterating only ETH candles.
Each `on_candle()` call verifies that the received candle timestamp equals the
next preloaded ETH timestamp, preventing a runner sequence from diverging from
the sequence validated against BTC. Extra calls and out-of-order calls fail
closed.

## Indicators And Causality

BTC context uses the existing `domain.market.indicators.ema` function with
periods 20 and 50. For index `i`, `BTC_BULLISH[i]` is true only when both EMA
values at `i` are ready and `EMA20[i] > EMA50[i]`. Because the existing EMA
implementation computes each element only from input positions `0..i`, batch
precomputation is causally equivalent to incremental calculation.

Before BTC EMA50 is ready, BTC context is unavailable. No forward fill,
interpolation, synthetic candle, nearest timestamp, or future value is used.
An explicit temporal-corruption test changes BTC candles after timestamp T and
asserts that context and decision behavior through T remain unchanged.

## Decision Rules

For every ETH candle, call `EmaRsiBaseline.on_candle()` exactly once.

- Baseline BUY plus ready bullish BTC context returns BUY with reason
  `ema_cross_up_btc_confirmed`.
- Baseline BUY plus bearish or unavailable BTC context returns HOLD with reason
  `btc_context_block`.
- Baseline SELL is returned unchanged, including its original reason and
  intensity, regardless of BTC state or BTC warmup.
- Baseline HOLD is returned unchanged, including its original reason and
  intensity, regardless of BTC state or BTC warmup.
- BTC never creates BUY and never forces SELL.

The baseline source, baseline config defaults, and protected runtime files are
not modified.

## Identity And Experiment Specification

Use the existing `StrategyDefinition`, `ImportlibSourceResolver`, and
`strategy_artifact_identity` APIs. The candidate definition declares its own
module source plus the composed baseline and reused indicator modules. Its
normalized configuration includes ETH baseline parameters and BTC EMA context
parameters. Changing BTC context configuration therefore changes
`StrategyArtifactIdentity` without any new identity mechanism.

Use the existing open-ended `ExperimentSpec.dataset` mapping with nested
`primary` and `context` entries. Each entry records dataset id, symbol,
timeframe, row start, and row end. Changing the BTC dataset identity or slice
changes `SpecId`; `ExperimentSpec` itself remains unchanged.

## Failure Behavior

Construction or execution raises `ValueError` before producing a misleading
decision when any invariant fails:

- primary/context length mismatch;
- missing or mismatched timestamp;
- mismatched adapter dataset, timeframe, or row range;
- empty aligned input;
- runner ETH timestamp diverges from the prevalidated sequence;
- runner provides more ETH candles than the validated sequence.

The implementation never substitutes missing context.

## Testing

Follow red-green-refactor. Unit tests cover all specified decision branches,
BTC warmup, complete alignment and fail-closed errors, temporal corruption,
determinism, artifact identity sensitivity, ExperimentSpec context sensitivity,
baseline source/config integrity, and FINAL_HOLDOUT denial. Integration tests
run the unchanged `LabSessionRunner` with separate ETH/BTC frozen adapters.
E2E coverage runs the complete DEVELOPMENT-only candidate path without
walk-forward or holdout access.

New Phase 18A production modules must reach 100% statement and branch coverage.
The complete lab, integration, E2E, and global suites must pass with global
coverage at least 90%, followed by ruff lint, ruff format check, and strict
mypy.

## Development Smoke

Run baseline and candidate through runtime-parity on identical ETH candles and
an exactly aligned BTC slice wholly inside DEVELOPMENT. Select a representative
range only to establish `BTC_BLOCKED_BUYS > 0`, never by PnL. Record baseline
BUY signals, context BUY signals, and blocked BUY count. Do not infer edge,
improvement, or promotability from the smoke.

## Evidence And Gate

Store Phase 18A definition, alignment, smoke JSON, test logs, coverage, lint,
format, and mypy evidence under `docs/phases/18A/evidence/`. Prepare
`docs/phases/18A/commit-candidate-001.md` with the exact diff and graph blast
radius. Keep every file unstaged and uncommitted. Do not push, run walk-forward,
or consume FINAL_HOLDOUT. Stop at `READY_FOR_HUMAN_18A_GATE`.

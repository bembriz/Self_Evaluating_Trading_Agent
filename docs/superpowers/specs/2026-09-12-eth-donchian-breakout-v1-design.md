# EthDonchianBreakout-v1 Design (Phase 19A)

Design-only phase. No strategy code, no indicator code, no economic evaluation,
no walk-forward, no holdout. This document fixes the new hypothesis and its
frozen parameters before any result is observed.

## Context

- Base commit: `75c353c`.
- Frozen historical artifacts that MUST NOT change: `baseline-v1`
  (`EmaRsiBaseline`), `EmaRsiBtcContext-v1`, `EmaRsiBtcRegime-v1`, `PaperEngine`,
  `RiskEngine`, `LabSessionRunner`, and the protected runtime.
- Prior BTC-context work (18A–18D) is closed. 19A starts a different family.

## Hypothesis

Capture directional ETH volatility expansion with a close-based Donchian
breakout gated by a trend-strength filter (ADX), instead of filtering an
existing EMA crossover. The strategy is a standalone ETH strategy, not a filter
on top of `baseline-v1`.

- Primary asset: `ETHUSDT` 15m.
- No `BTCUSDT`. No LLM. No ML. No multi-timeframe.

## Scope And Constraints

- One new deterministic strategy: `EthDonchianBreakout-v1`.
- Frozen dataset: `BYBIT_ETHBTC_V001`.
- Later evaluation uses DEVELOPMENT `[0, 62208)` only.
- `RiskEngine` remains unchanged and retains absolute authority over every order.
- No parameter search, no tuning, no alternative lookbacks, no alternative ADX
  thresholds.
- No code, no economic evaluation, no walk-forward, no holdout in 19A.

## Exact Entry / Exit Semantics

Let `t` be the index of the current candle. The current candle is always
**excluded** from the Donchian window; only strictly prior candles participate.

### Entry (BUY)

```
prior_high[t] = max(high[t - ENTRY_DONCHIAN_LOOKBACK : t])   # t-20 .. t-1
BUY  iff  close[t] > prior_high[t]
     AND  adx14[t] is available
     AND  adx14[t] > ADX_MIN
```

- `high[t-20:t]` contains exactly the 20 bars immediately before `t`; `high[t]`
  is never included.
- `close[t]` is the confirmed close of the current bar.
- Strict inequality: `close[t] == prior_high[t]` does not trigger a BUY.

### Exit (SELL)

```
prior_low[t] = min(low[t - EXIT_DONCHIAN_LOOKBACK : t])      # t-10 .. t-1
SELL iff  close[t] < prior_low[t]
```

- `low[t-10:t]` contains exactly the 10 bars immediately before `t`; `low[t]` is
  never included.
- Strict inequality: `close[t] == prior_low[t]` does not trigger a SELL.
- The SELL condition does not depend on ADX.
- The strategy does not track position state; the `RiskEngine`/`PaperEngine`
  reject a SELL when there is no open position (long-only), exactly as with
  `baseline-v1`.

### Otherwise

`HOLD`.

## ADX Definition (new causal indicator)

`ADX` does not exist in `domain.market.indicators`; the implementation phase must
add a causal Wilder ADX consistent with the existing smoothing conventions
(`atr`/`rsi`). Definition for period `n = ADX_PERIOD`:

- `TR[t]` as in `atr` (true range).
- `up[t] = high[t] - high[t-1]`, `down[t] = low[t-1] - low[t]`.
- `+DM[t] = up[t] if up[t] > down[t] and up[t] > 0 else 0`.
- `-DM[t] = down[t] if down[t] > up[t] and down[t] > 0 else 0`.
- Wilder-smooth `TR`, `+DM`, `-DM` over `n` (seed = sum/average of the first `n`
  values from index 1, then `avg = (avg*(n-1) + x)/n`), matching `atr`.
- `+DI = 100 * smoothed(+DM) / smoothed(TR)`,
  `-DI = 100 * smoothed(-DM) / smoothed(TR)`.
- `DX = 100 * |+DI - -DI| / (+DI + -DI)` (0 when `+DI + -DI == 0`).
- The function returns `list[float | None]`, `None` while unavailable, and is
  causal: `ADX[t]` uses only candles `0..t`.

Exact indexing for period `n` (frozen):

- TR / `+DM` / `-DM` observations start at index `1`.
- First Wilder-smoothed TR / `+DM` / `-DM`: index `n`, using observations
  `1..n`.
- First `+DI` / `-DI`: index `n`.
- First `DX`: index `n`.
- First `ADX`: index `2n - 1`, using `DX` values `n..2n-1` inclusive, seeded as
  their Wilder average.
- Subsequent smoothing:
  `avg[t] = (avg[t-1] * (n - 1) + value[t]) / n`.
- Flat/zero-denominator `+DI + -DI == 0` fails safely to `DX = 0`.

For `n = 14`: `FIRST_ADX_INDEX = 27`.

ADX availability affects BUY only. When a BUY decision needs ADX and it is
unavailable, the BUY is blocked (fail closed). SELL never depends on ADX.

## Causality

- Entry uses `close[t]` (confirmed at bar close) and `high[t-20:t]` (past only).
- Exit uses `close[t]` and `low[t-10:t]` (past only).
- ADX at `t` is computed only from candles `0..t`.
- No future candle, forward fill, interpolation, nearest timestamp, or synthetic
  value is used. A temporal-corruption test mutates candles strictly after `T`
  and asserts that signals through `T` are unchanged.

## Warmup

Warmup is frozen explicitly. ADX availability affects BUY only; SELL must never
depend on ADX readiness.

| Condition | BUY | SELL |
|---|---|---|
| `t < 10` | unavailable → HOLD | unavailable → HOLD |
| `10 <= t < 20` | unavailable → HOLD | may trigger from `prior_low_10` |
| `t >= 20` and ADX unavailable | blocked → HOLD | may still trigger from `prior_low_10` |
| `t >= 20` and ADX available | evaluated normally | evaluated normally |

- BUY requires: entry Donchian window ready (`t >= 20`) **and** ADX available
  **and** `close[t] > prior_high_20` **and** `adx14[t] > 20`.
- SELL requires only: exit Donchian window ready (`t >= 10`) **and**
  `close[t] < prior_low_10`.
- No global warmup suppresses valid SELL signals. No partial or forward-filled
  window is used; unavailable inputs yield HOLD only for the signal that depends
  on them.
- No `baseline-v1` warmup behavior is involved (this strategy does not compose
  the EMA/RSI baseline).

## Frozen Parameters (Predeclared)

| Parameter | Value | Notes |
|---|---|---|
| `entry_donchian_lookback` | 20 | prior highs, current bar excluded |
| `exit_donchian_lookback` | 10 | prior lows, current bar excluded |
| `adx_period` | 14 | Wilder |
| `adx_min` | 20 | strict `>` |

No value may be changed by search, tuning, or post-hoc reasoning. A different
value requires a new strategy version and a new experiment.

## Identity

- Strategy name: `EthDonchianBreakout`.
- Strategy version: `eth-donchian-breakout-v1`.
- New module (future implementation): `src/lab/strategies/eth_donchian_breakout.py`.
- Uses the existing `StrategyDefinition` / `strategy_artifact_identity` APIs;
  no new fingerprint system.
- `normalized_config`: `entry_donchian_lookback`, `exit_donchian_lookback`,
  `adx_period`, `adx_min`. Changing any of them changes
  `StrategyArtifactIdentity`.
- `sources`: `lab.strategies.eth_donchian_breakout`, `domain.market.indicators`
  (the latter also carries the new `adx`). `baseline-v1` is not a source because
  this strategy does not compose it.
- `ExperimentSpec.dataset` uses the existing open-ended mapping with the ETH
  primary slice; no `context` entry (no BTC).
- The three frozen strategy artifacts are not imported for composition and are
  not modified.

## Decision Rules Summary

- BUY: `close[t] > max(high[t-20:t])` and `adx14[t] > 20` (ADX available).
- SELL: `close[t] < min(low[t-10:t])`.
- HOLD: otherwise, including all warmup/unavailable states.
- `RiskEngine` may still reject any signal (position limits, drawdown, daily
  loss, stop requirements); the strategy never bypasses it.

## Failure Behavior

Construction or execution raises `ValueError` before producing a misleading
decision when any invariant fails: non-positive parameters, invalid lookbacks,
mismatched or out-of-order candle sequences, or a runner candle that does not
match the preloaded sequence. Missing indicator values are handled as warmup
(HOLD), never substituted.

## Testing Strategy (for the later implementation phase)

- **Unit (new strategy + new `adx`):**
  - entry boundary: `close[t] > prior_high` triggers BUY; `close[t] == prior_high`
    does not; current candle's high never participates.
  - ADX gate: `adx14[t] <= 20` blocks BUY; `adx14[t] > 20` allows it; ADX
    unavailable blocks BUY.
  - exit boundary: `close[t] < prior_low` triggers SELL; equality does not;
    current candle's low never participates.
  - warmup: `t < 10` → HOLD for both; `10 <= t < 20` → BUY unavailable but SELL
    may trigger; `t >= 20` with ADX unavailable → BUY blocked but SELL may
    trigger.
  - causal corruption: future candles do not change past signals.
  - determinism: identical input yields identical signals.
  - identity sensitivity to each parameter; exact `sources` tuple.
  - `adx` unit tests: warmup `None`, monotonic trending series yields high ADX,
    flat series yields low ADX, causal prefix equality.
  - frozen artifacts untouched and FINAL_HOLDOUT denied.
- **Integration:** real `FrozenDatasetAdapter` + unchanged `LabSessionRunner` +
  `PaperEngine`; reproducibility by double run.
- **E2E:** complete DEVELOPMENT-only path; no walk-forward request; holdout
  remains `PRISTINE`.
- New production modules (strategy and the `adx` addition) must reach 100%
  statement and branch coverage; global coverage ≥ 90%; ruff, ruff format, and
  strict mypy must pass.

## Future DEVELOPMENT Evaluation Criteria (predeclared)

- Run on full DEVELOPMENT `[0, 62208)` with runtime-parity and identical
  economic conditions to `baseline-v1` (same engine config, capital, fees,
  slippage, timing model).
- PRIMARY comparison: `EthDonchianBreakout-v1` vs `baseline-v1`, reusing the
  predeclared classification with no composite score:
  - `IMPROVED` iff expectancy, profit factor, and net PnL improve and max
    drawdown does not worsen by more than `0.01` absolute;
  - `NOT_IMPROVED` if no economic metric improves or at least two of the three
    (expectancy, profit factor, net PnL) deteriorate;
  - otherwise `MIXED`.
- `WALK_FORWARD_CANDIDATE = YES` only if `DEVELOPMENT_RESULT = IMPROVED`, and
  only subject to explicit human approval. Parameters stay frozen; no tuning.
- `EDGE_PRESENT` and `STRATEGY_PROMOTABLE` remain `NOT_EVALUATED` until
  walk-forward.

## Non-Goals

- No BTC context, no LLM, no ML, no MACD/other filters, no parameter search,
  no grid search, no multi-timeframe.
- No strategy code, tests, or execution in 19A.
- No PnL, backtest, walk-forward, or holdout access.
- No modification of `baseline-v1`, `EmaRsiBtcContext-v1`,
  `EmaRsiBtcRegime-v1`, `PaperEngine`, `RiskEngine`, `LabSessionRunner`, or the
  protected runtime.

## Evidence And Gate

Deliverable is this design document only, at
`docs/superpowers/specs/2026-09-12-eth-donchian-breakout-v1-design.md`. Keep the
working tree otherwise unchanged: no staging, no commit, no push, no
walk-forward, no holdout. Stop at `READY_FOR_HUMAN_PHASE_19A_DESIGN_GATE`.

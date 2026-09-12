# EmaRsiBtcRegime-v1 Design (Phase 18C)

Design-only phase. No strategy code, no economic evaluation, no walk-forward, no
holdout. This document fixes the next BTC-context hypothesis **before** any
economic result is observed.

## Context

- Base commit: `6743a79`.
- `EmaRsiBtcContext-v1` closed 18B with `DEVELOPMENT_RESULT=MIXED` and
  `WALK_FORWARD_CANDIDATE=NO`. It is frozen and must not be modified.
- `baseline-v1` (`EmaRsiBaseline`) is the frozen ETH reference and must not be
  modified.
- `EmaRsiBtcContext-v1` added only the trend **level** (`BTC EMA20 > EMA50`) as
  BTC context. 18C explores adding one orthogonal, still-simple dimension.

## Goal

Propose at most three simple hypotheses for using `BTCUSDT` as context for
`ETHUSDT` entries, compare them on design principles only, and select one.

## Hard Constraints (apply to every hypothesis)

- Trade `ETHUSDT` only; `BTCUSDT` is context only.
- Keep `baseline-v1` ETH logic intact; filter BUY only.
- Causal: only information available at or before `t`.
- Later evaluation uses DEVELOPMENT `[0, 62208)` exclusively.
- No LLM, no ML, no MACD, no ADX, no correlation optimization, no grid search,
  no parameter search, no multi-timeframe.
- No economic result may be consulted to choose the hypothesis.

## Hypotheses Considered

All three extend the v1 gate `BTC EMA20 > EMA50` with exactly one extra causal
condition. `EMA20`/`EMA50` are the existing `domain.market.indicators.ema`
values on `BTCUSDT` 15m closes.

### A. Trend + Slope

```
BTC_RISK_ON[t] = EMA20[t] > EMA50[t]  AND  EMA20[t] > EMA20[t-4]
```

- Economic interpretation: the trend exists **and** the fast mean is still
  rising (trend direction / acceleration), not merely above the slow mean.
- New information vs v1: trend **direction**, orthogonal to the level
  comparison.

### B. Trend + Price Confirmation

```
BTC_RISK_ON[t] = EMA20[t] > EMA50[t]  AND  close[t] > EMA20[t]
```

- Economic interpretation: the trend exists **and** price is currently holding
  above the fast mean (trend intact on the current bar).
- New information vs v1: current price position relative to the fast mean.

### C. Trend + Momentum

```
BTC_RISK_ON[t] = EMA20[t] > EMA50[t]  AND  (close[t] / close[t-4] - 1) > 0
```

- Economic interpretation: the trend exists **and** recent short-window return
  is positive.
- New information vs v1: short-horizon momentum.

## Design-Principle Comparison (no PnL)

| Criterion | A. Trend + Slope | B. Trend + Price | C. Trend + Momentum |
|---|---|---|---|
| Economic meaning | Regime persistence / acceleration | Trend intact on current bar | Recent momentum |
| Causality | Causal (`<= t`) | Causal (`<= t`) | Causal (`<= t`) |
| Simplicity | One predeclared lookback | No new parameter | One predeclared window |
| Redundancy with `EMA20 > EMA50` | Low (slope orthogonal to level) | High (price usually sits above EMA20 when EMA20 > EMA50) | Medium (momentum overlaps slope) |
| Expected sensitivity | Low (EMA-difference is smooth) | High (single close vs mean can whipsaw) | Medium-high (endpoint-sensitive) |
| Overfit risk | Low (one integer, zero threshold) | Low parameters but noisy signal | Higher (two endpoints + window) |
| Reproducibility | Fully deterministic | Fully deterministic | Fully deterministic |
| Difference vs v1 | Clear (adds slope) | Modest (confirmation) | Clear (adds momentum) |

## Selected Hypothesis

**A. Trend + Slope.**

Rationale, from principles only:

- It is the **simplest hypothesis that adds non-redundant information**: a
  single predeclared integer (`lookback = 4`) and a zero threshold
  (`EMA20[t] > EMA20[t-4]`), with no tuned cutoff.
- B is simpler in parameter count but its condition is largely redundant with
  `EMA20 > EMA50`, so it adds little new information and is more prone to
  whipsaw from a single close.
- C adds momentum but is endpoint-sensitive (`close[t]` vs `close[t-4]`), a
  noisier proxy for what A measures more smoothly via the EMA difference.
- A reuses the already-frozen BTC EMA20/50 periods, so it introduces no new
  indicator family and no new framework.

`EmaRsiBtcContext-v1` remains the level-only baseline; `EmaRsiBtcRegime-v1`
tests whether trend **direction** adds value beyond trend **level**.

## Exact Rule

For each ETH candle at index `i`:

```
BTC_RISK_ON[i] =
    btc_ema20[i] is ready
    AND btc_ema50[i] is ready
    AND btc_ema20[i-4] is ready            (i >= 4)
    AND btc_ema20[i] > btc_ema50[i]
    AND btc_ema20[i] > btc_ema20[i-4]
```

`BTC_RISK_ON` is `False` whenever any required EMA value is unavailable or the
lookback index is out of range.

## Frozen Parameters (Predeclared)

| Parameter | Value | Notes |
|---|---|---|
| `ema_fast` (ETH) | 20 | identical to `baseline-v1` |
| `ema_slow` (ETH) | 50 | identical to `baseline-v1` |
| `rsi_period` (ETH) | 14 | identical to `baseline-v1` |
| `rsi_exit` (ETH) | 80.0 | identical to `baseline-v1` |
| `btc_ema_fast` | 20 | reused from v1 |
| `btc_ema_slow` | 50 | reused from v1 |
| `btc_slope_lookback` | 4 | new; candles (15m) |

No value may be changed by search, tuning, or post-hoc reasoning. A different
value requires a new strategy version and a new experiment.

## Causality

- `btc_ema20[i]` and `btc_ema50[i]` come from the existing EMA implementation,
  which computes each element only from input positions `0..i`; batch
  precomputation is causally equivalent to incremental calculation.
- `btc_ema20[i-4]` is strictly past data.
- The gate is evaluated at `t` using only BTC closes at or before `t` and the
  current ETH candle; no future candle, forward fill, interpolation, nearest
  timestamp, or synthetic value is used.
- A temporal-corruption test mutates BTC candles strictly after `T` and asserts
  that context and decisions through `T` are unchanged.

## Warmup Behavior

- BTC EMA20 is ready after 20 samples; BTC EMA50 after 50 samples; the slope
  needs `btc_ema20[i-4]`, available once EMA20 is ready and `i >= 4`.
- Binding constraint: `BTC_RISK_ON` is undefined until EMA50 is ready.
- While BTC context is unavailable, `BTC_RISK_ON = False`, so candidate BUY
  signals are blocked (fail closed). SELL and HOLD are unaffected.
- No ETH baseline warmup behavior changes.

## Decision Rules (BUY / SELL / HOLD)

For every ETH candle, call `EmaRsiBaseline.on_candle()` exactly once.

- Baseline BUY and `BTC_RISK_ON = True` → BUY, reason
  `ema_cross_up_btc_regime_confirmed`.
- Baseline BUY and (`BTC_RISK_ON = False` or unavailable) → HOLD, reason
  `btc_regime_block`.
- Baseline SELL → returned unchanged (reason and intensity preserved),
  regardless of BTC state or warmup.
- Baseline HOLD → returned unchanged (reason and intensity preserved),
  regardless of BTC state or warmup.
- BTC never creates a BUY and never forces a SELL.

## Identity

- Strategy name: `EmaRsiBtcRegime`.
- Strategy version: `ema-rsi-btc-regime-v1`.
- New module (future implementation): `src/lab/strategies/ema_rsi_btc_regime.py`.
- Composes a fresh `EmaRsiBaseline`; does not modify `EmaRsiBaseline` or
  `EmaRsiBtcContext-v1`, which remain frozen historical artifacts.
- Uses the existing `StrategyDefinition` / `strategy_artifact_identity` APIs.
  `normalized_config` includes the ETH baseline parameters plus
  `btc_ema_fast`, `btc_ema_slow`, and `btc_slope_lookback`. Changing any of them
  changes `StrategyArtifactIdentity` with no new identity mechanism.
- `sources`: `lab.strategies.ema_rsi_btc_regime`, `domain.trading.strategy`,
  `domain.market.indicators`.
- `ExperimentSpec.dataset` keeps the existing nested `primary` / `context`
  mapping, with `context` recording `BTCUSDT` 15m and the same row slice.

## Failure Behavior

Construction or execution raises `ValueError` before producing a misleading
decision when any invariant fails: primary/context length mismatch; missing or
mismatched timestamp; mismatched adapter dataset, timeframe, or row range; empty
aligned input; invalid parameters (`<= 0` periods, `ema_fast >= ema_slow`,
`btc_ema_fast >= btc_ema_slow`, `btc_slope_lookback < 1`); runner ETH timestamp
diverging from the prevalidated sequence; runner providing more ETH candles than
validated. Missing context is never substituted.

## Testing Strategy (for the later implementation phase)

- **Unit:** every decision branch (RISK_ON true → BUY; RISK_ON false → HOLD;
  SELL preserved under bullish, bearish, and warmup context; HOLD preserved
  exactly); warmup (EMA50 not ready, slope not ready); causal corruption
  (future BTC changes do not alter past decisions); determinism; alignment and
  fail-closed errors; parameter validation; artifact-identity sensitivity to
  `btc_slope_lookback` and BTC periods; `baseline-v1` defaults and source
  integrity; `SpecId` sensitivity to the BTC context slice; FINAL_HOLDOUT
  denial.
- **Integration:** real `FrozenDatasetAdapter` for ETH and BTC with the
  unchanged `LabSessionRunner`, reproducibility, and fail-closed adapter
  mismatches.
- **E2E:** complete DEVELOPMENT-only candidate path, no walk-forward request,
  holdout remains `PRISTINE`.
- New production modules must reach 100% statement and branch coverage; global
  coverage ≥ 90%; ruff, ruff format, and strict mypy must pass.

## Development Evaluation Criterion (predeclared for the later phase)

- Run on full DEVELOPMENT `[0, 62208)` with the real `FrozenDatasetAdapter` +
  `LabSessionRunner` + `PaperEngine` + `RiskEngine`, identical economic
  conditions for both strategies (same engine config, capital, fees, slippage,
  timing model, and ETH baseline parameters).
- Compare `EmaRsiBtcRegime-v1` against `baseline-v1` (and against
  `EmaRsiBtcContext-v1` for context), reusing the 18B predeclared
  classification with no composite score:
  - `IMPROVED` iff expectancy, profit factor, and net PnL improve and max
    drawdown does not worsen by more than `0.01` absolute;
  - `NOT_IMPROVED` if no metric improves or at least two of the three economic
    metrics deteriorate;
  - otherwise `MIXED`.
- Record BTC filter attribution (baseline BUY candidates = confirmed + blocked)
  as **descriptive only**; blocking an entry changes the later portfolio path,
  so it is not a perfect counterfactual.
- `WALK_FORWARD_CANDIDATE = YES` only if `DEVELOPMENT_RESULT = IMPROVED`, and
  only subject to explicit human approval. Parameters stay frozen at the values
  above; no tuning. `EDGE_PRESENT` and `STRATEGY_PROMOTABLE` remain
  `NOT_EVALUATED` until walk-forward.

## LLM

`LLM_STATUS=DEFERRED`. Rationale: first measure how much value deterministic
BTC context can add. This yields a clean ladder for later incremental
attribution:

```
baseline-v1
vs EmaRsiBtcContext-v1   (BTC trend level)
vs EmaRsiBtcRegime-v1    (BTC trend level + slope)
vs BTC context + LLM     (future)
```

so the marginal contribution of the LLM can be isolated. No LLM enters 18C or
the immediate deterministic evaluation.

## Non-Goals

- No strategy code, tests, or execution in 18C.
- No PnL, backtest, walk-forward, or holdout access.
- No MACD, ADX, ML, LLM, correlation optimization, grid search, parameter
  search, or multi-timeframe.
- No modification of `EmaRsiBaseline` or `EmaRsiBtcContext-v1`.

## Evidence And Gate

Deliverable is this design document only, at
`docs/superpowers/specs/2026-09-12-btc-regime-v1-design.md`. Keep the working
tree otherwise unchanged: no staging, no commit, no push, no walk-forward, no
holdout. Stop at `READY_FOR_HUMAN_18C_DESIGN_GATE`.

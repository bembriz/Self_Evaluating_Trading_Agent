# EthBollingerMeanReversion-v1 Design (Phase 20A)

Design-only phase. No code, no economic evaluation, no walk-forward, no holdout.
This document freezes the hypothesis, the exact rules and the parameters before
any result is observed.

## Context

- Base commit: `e521687`.
- `PHASE_19C_CLOSED=YES`; the Absolute Viability Gate is implemented.
- `HOLDOUT_STATE=PRISTINE`.
- Frozen historical strategies that MUST NOT change: `EmaRsiBaseline`,
  `EmaRsiBtcContext-v1`, `EmaRsiBtcRegime-v1`, `EthDonchianBreakout-v1`, the
  approved `adx` indicator, `PaperEngine`, `RiskEngine`, `LabSessionRunner` and
  the protected runtime.

## Hypothesis

Short-horizon **mean reversion** in **non-trending** ETH markets: when price
temporarily closes below a volatility envelope and then **re-enters** that
envelope while directional trend strength is low, price may revert toward its
rolling mean.

**Do NOT buy merely because price is below the lower band.** The entry requires
the re-entry confirmation.

## Economic Rationale

- A close below the lower Bollinger Band marks a volatility excursion
  (overextension) without claiming a trend.
- Re-entering the band is evidence that the excursion is fading rather than
  continuing.
- A low ADX (< 20) restricts the setup to non-trending / ranging regimes, where
  mean reversion is the more plausible behaviour; in strong trends, band breaks
  tend to continue.
- The exit at the middle band captures the reversion toward the rolling mean.

## Market

- Primary: `ETHUSDT` 15m.
- No BTC context. No LLM. No ML. No multi-timeframe.

## Frozen Parameters

| Parameter | Value |
|---|---|
| `bollinger_period` | 20 |
| `bollinger_stddev_multiplier` | 2.0 |
| `adx_period` | 14 |
| `adx_max` | 20.0 |

No parameter search, optimization, or alternative thresholds. A different value
requires a different future strategy version and a new experiment.

## Exact Bollinger Definition

For period `n = 20` and the confirmed close series:

```
MIDDLE[t] = mean(close[t-n+1 : t+1])
STD[t]    = population standard deviation of the same n closes   (ddof = 0)
UPPER[t]  = MIDDLE[t] + 2.0 * STD[t]
LOWER[t]  = MIDDLE[t] - 2.0 * STD[t]
```

- The **current confirmed close** `close[t]` is included. This is intentional.
- `ddof = 0` (population standard deviation).
- Only candles `<= t` are used.
- First available index: `19` (`n - 1`).
- No future values, no interpolation, no forward fill.

## Exact BUY Semantics

A BUY candidate exists iff all hold:

```
close[t-1] <  LOWER[t-1]      (strict: oversold excursion)
close[t]   >= LOWER[t]        (inclusive: re-entry confirmation)
ADX14[t]   is available
ADX14[t]   <  20.0            (strict: low directional trend strength)
```

- `ADX14[t] == 20.0` does **not** pass.
- `close[t] == LOWER[t]` **does** satisfy the re-entry condition.
- `close[t-1] == LOWER[t-1]` does **not** satisfy the excursion condition.

## Exact SELL Semantics

A SELL candidate exists iff:

```
close[t] >= MIDDLE[t]
```

- The exit does **not** depend on ADX.
- The exit does **not** depend on RSI.
- The strategy does not track portfolio position; `PaperEngine` / `RiskEngine`
  remain authoritative, and a SELL without an open position may be rejected as
  normal.

## Decision Precedence (frozen)

SELL takes precedence over BUY. Evaluation order for each candle `t`:

1. If `MIDDLE[t]` is available AND `close[t] >= MIDDLE[t]` → return **SELL**.
2. Otherwise, if `LOWER[t-1]`, `LOWER[t]` and `ADX[t]` are available AND
   `close[t-1] < LOWER[t-1]` AND `close[t] >= LOWER[t]` AND `ADX[t] < 20.0`
   → return **BUY**.
3. Otherwise → return **HOLD**.

Rationale: the thesis is mean reversion toward the middle band. If the current
close has already reached or exceeded `MIDDLE[t]`, the intended reversion target
has already been reached; opening a new BUY at that point would contradict the
strategy hypothesis.

`SELL_PRECEDENCE_OVER_BUY=YES`.

## Warmup

- Bollinger first available at index `19`.
- ADX14 first available at index `27`.
- BUY requires `LOWER[t-1]`, `LOWER[t]` and `ADX14[t]`, so BUY is unavailable
  until all exist; effectively constrained by ADX (`t >= 27`).
- SELL requires only `MIDDLE[t]`, so SELL may be emitted once Bollinger is ready
  (`t >= 19`), **independent of ADX readiness**.
- No global ADX warmup suppresses valid SELL signals. Unavailable inputs yield
  HOLD only for the signal that depends on them.

## Why No RSI In v1

RSI is intentionally excluded from v1. Being outside the lower Bollinger Band
already expresses price overextension; adding RSI immediately could introduce
redundant filtering and make attribution harder. The first experiment isolates:

```
volatility excursion / re-entry
+
trend-regime filter (ADX < 20)
```

If this hypothesis fails, RSI must **not** be tuned into it during the same
experiment.

## ADX

Reuse the existing approved causal Wilder `adx` implementation. Do **not** modify
ADX. ADX is used only as a range/regime filter (`ADX < 20`): no ADX slope, no
`+DI`/`-DI` directional condition.

## Strategy Architecture

- Standalone strategy; it does **not** compose `EmaRsiBaseline`,
  `EmaRsiBtcContext-v1`, `EmaRsiBtcRegime-v1` or `EthDonchianBreakout-v1`.
- Strategy name: `EthBollingerMeanReversion`.
- Strategy version: `eth-bollinger-mean-reversion-v1`.
- Future module: `src/lab/strategies/eth_bollinger_mean_reversion.py`.

## Indicator Implementation Requirement

`domain.market.indicators` has **no** Bollinger Bands and no rolling population
standard deviation (`realized_volatility` uses `ddof=1` on returns, which is not
reusable here). The minimum causal addition required in the later implementation
phase is one small function, consistent with existing conventions:

```
bollinger(values: Sequence[float], period: int = 20, multiplier: float = 2.0)
    -> BollingerBands
```

where `BollingerBands` is a frozen dataclass with three `list[float | None]`
fields (`middle`, `upper`, `lower`), each `None` before index `period - 1`,
computed causally from `values[0..i]`. It uses `statistics.pstdev` (stdlib,
`ddof=0`); no numpy/pandas dependency is introduced.

This is the only indicator addition required. The implementation phase must not
modify `adx` or any other existing indicator.

## Causality

- `LOWER[t-1]` uses closes `<= t-1`.
- `LOWER[t]` uses closes `<= t`.
- `ADX[t]` uses candles `<= t`.
- `MIDDLE[t]` uses closes `<= t`.

No future candle may affect a decision at `t`. A future-candle corruption test is
mandatory in the later implementation.

## Identity

Reuse `StrategyDefinition`, `strategy_artifact_identity` and `ExperimentSpec`.
No new fingerprint system.

- `normalized_config`: `bollinger_period`, `bollinger_stddev_multiplier`,
  `adx_period`, `adx_max`.
- `sources`: `lab.strategies.eth_bollinger_mean_reversion`,
  `domain.market.indicators`.
- `ExperimentSpec.dataset`: `ETHUSDT` 15m, primary only. No BTC context entry.

## Failure Behavior

Construction or execution raises `ValueError` before producing a misleading
decision when any invariant fails: non-positive period, non-positive multiplier,
runner candle not matching the preloaded sequence, or exhausted sequence.
Unavailable indicator values are warmup (HOLD), never substituted. The strategy
never bypasses `RiskEngine`.

## Risk

`RiskEngine` remains unchanged and retains absolute authority. Do not modify risk
sizing, daily loss, drawdown, position limits, fees, slippage, stops or the kill
switch.

## Test Strategy (later implementation)

Bollinger:

1. first ready index = 19.
2. population stddev `ddof=0` (hand-computed fixture).
3. exact middle/upper/lower values on a hand-computable fixture.
4. flat prices → stddev 0 and bands equal the mean.
5. causal prefix equality.
6. future mutation cannot change past bands.
7. invalid period / multiplier behavior.

Strategy:

8. excursion + re-entry + `ADX < 20` → BUY.
9. `previous_close == previous_lower_band` → no BUY.
10. `current_close < current_lower_band` → no BUY.
11. `current_close == lower_band` → re-entry condition passes.
12. `ADX < 20` → gate passes.
13. `ADX == 20` → gate fails.
14. `ADX > 20` → gate fails.
15. ADX unavailable → BUY blocked.
16. `close >= middle_band` → SELL.
17. SELL independent of ADX.
18. Bollinger warmup → correct HOLD behavior (BUY blocked, SELL allowed from 19).
19. future corruption → unchanged past decisions.
20. determinism.
21. identity sensitivity (each parameter).
22. SpecId sensitivity.
23. FINAL_HOLDOUT denied.
24. same candle satisfies re-entry BUY conditions AND `close[t] >= MIDDLE[t]`
    → SELL (precedence).
25. SELL behavior is identical regardless of ADX: unavailable, `< 20`, `== 20`,
    `> 20`.

Integration: real `FrozenDatasetAdapter` + unchanged `LabSessionRunner` +
`RiskEngine` + `PaperEngine`; reproducibility by double run.

E2E: DEVELOPMENT-only.

New production code (strategy and the `bollinger` addition) must reach 100%
statement and branch coverage.

## Future DEVELOPMENT Evaluation

Later evaluation uses the full DEVELOPMENT `[0, 62208)` under identical economic
conditions to `baseline-v1`.

PRIMARY comparison: `EthBollingerMeanReversion-v1` vs `baseline-v1`, using the
existing relative classification (`IMPROVED` / `MIXED` / `NOT_IMPROVED`) with the
predeclared rule unchanged.

## Phase 19C Absolute Viability Gate

Because Phase 19C is active, future walk-forward eligibility additionally
requires:

```
NET_PNL > 0
EXPECTANCY > 0
PROFIT_FACTOR > 1.0
```

all finite. Therefore:

```
WALK_FORWARD_ELIGIBLE = YES  iff
    DEVELOPMENT_RESULT == IMPROVED
    AND
    ABSOLUTE_VIABILITY_GATE == PASS
```

Even then, `WALK_FORWARD_AUTHORIZED` requires explicit human approval. Public
`FrozenDatasetAdapter` access to WALK_FORWARD remains denied by default; only
`guarded_walk_forward_open` may open it.

## Non-Goals

No RSI, no BTC, no LLM, no MACD, no additional volume filter, no parameter
search, no grid search, no optimization, no multi-timeframe, no alternative
Bollinger periods, no alternative standard-deviation multiplier, no alternative
ADX threshold.

## Safety

- `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0`, `FINAL_HOLDOUT_EXECUTIONS=0`,
  `HOLDOUT_STATE=PRISTINE`.
- Do not open real WALK_FORWARD; do not open FINAL_HOLDOUT.
- No code, no staging, no commit, no push.

## Evidence And Gate

Deliverable is this design document only, at
`docs/superpowers/specs/2026-09-12-eth-bollinger-mean-reversion-v1-design.md`.
Stop at `READY_FOR_HUMAN_PHASE_20A_DESIGN_GATE`.

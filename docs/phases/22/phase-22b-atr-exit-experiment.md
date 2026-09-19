# Phase 22-B — REAL ATR STOP / TARGET EXPERIMENT

> **Status:** COMPLETE
> **Date:** 2026-09-18
> **Role:** Trading Systems Audit / Evidence Engineer

---

## 1. Objective

Measure how many trades hit real Stop Loss and Take Profit when the Risk Engine receives real ATR. This is a NEW DEVELOPMENT experiment — it does NOT replace or modify the authoritative Phase 21R population.

---

## 2. Configuration

| Parameter | Value | Source |
|---|---|---|
| `stop_loss_required` | `True` | Experimental |
| `version` | `risk-v2-atr-exit` | New experimental config |
| `capital` | 1000.0 | Default |
| `stop_atr_multiplier` | 2.0 | RiskConfig default |
| `take_profit_r_multiple` | 2.0 | RiskConfig default |
| `trailing_atr_multiplier` | 3.0 | RiskConfig default |
| ATR period | 14 | Canonical (`indicators.py:122`) |
| Fee model | 10 bps taker/maker | Bybit spot v1 |
| Slippage | 2 bps | Conservative v1 |

---

## 3. Engine Exit Classification

| Label | exit_reason | Meaning |
|---|---|---|
| `INITIAL_OR_BELOW_ENTRY_STOP_EXIT` | `stop_loss` | Engine closed via stop_loss while active stop was at or below entry; this is not necessarily the immutable initial stop |
| `PROFIT_TRAILING_EXIT` | `trailing_stop` | Price hit trailing stop above entry (protecting profits) |
| `TAKE_PROFIT_EXIT` | `take_profit` | Price reached target (entry + 2*ATR) |
| `STRATEGY_EXIT` | `llm_sell` | Strategy/LLM decided to sell |

---

## 4. Results Per Strategy

### 4.1 baseline (634 trades)

**Engine Exits:**

| Exit Reason | Count | Rate |
|---|---|---|
| stop_loss | 324 | 51.1% |
| take_profit | 155 | 24.4% |
| trailing_stop | 62 | 9.8% |
| llm_sell | 93 | 14.7% |

**PnL by Exit Reason:**

| Exit Reason | Count | Avg Net | Total Net | Win Rate | Avg Hold (bars) |
|---|---|---|---|---|---|
| llm_sell | 93 | -0.1152 | -10.71 | 8.6% | 6.0 |
| stop_loss | 324 | -0.2129 | -68.98 | 0.0% | 16.1 |
| take_profit | 155 | +0.3605 | +55.88 | 100.0% | 22.5 |
| trailing_stop | 62 | +0.0118 | +0.73 | 46.8% | 42.8 |

**Net PnL:** -23.08

### 4.2 donchian (841 trades)

**Engine Exits:**

| Exit Reason | Count | Rate |
|---|---|---|
| stop_loss | 326 | 38.8% |
| take_profit | 199 | 23.7% |
| trailing_stop | 36 | 4.3% |
| llm_sell | 280 | 33.3% |

**PnL by Exit Reason:**

| Exit Reason | Count | Avg Net | Total Net | Win Rate | Avg Hold (bars) |
|---|---|---|---|---|---|
| llm_sell | 280 | -0.0886 | -24.82 | 17.5% | 20.3 |
| stop_loss | 326 | -0.2398 | -78.17 | 0.0% | 11.2 |
| take_profit | 199 | +0.3813 | +75.89 | 100.0% | 18.8 |
| trailing_stop | 36 | -0.0249 | -0.90 | 16.7% | 31.0 |

**Net PnL:** -28.00

### 4.3 bollinger (394 trades)

**Engine Exits:**

| Exit Reason | Count | Rate |
|---|---|---|
| stop_loss | 116 | 29.4% |
| take_profit | 2 | 0.5% |
| trailing_stop | 0 | 0.0% |
| llm_sell | 276 | 70.1% |

**PnL by Exit Reason:**

| Exit Reason | Count | Avg Net | Total Net | Win Rate | Avg Hold (bars) |
|---|---|---|---|---|---|
| llm_sell | 276 | +0.0343 | +9.46 | 65.2% | 6.9 |
| stop_loss | 116 | -0.2336 | -27.09 | 0.0% | 7.3 |
| take_profit | 2 | +0.3407 | +0.68 | 100.0% | 4.0 |

**Net PnL:** -16.96

---

## 5. Fixed-Level Intrabar Touch Audit

### 5.1 Trade-Level Counts (unique trades, may overlap)

| Metric | baseline (634) | donchian (841) | bollinger (394) |
|---|---|---|---|
| TARGET_TOUCHED_TRADES | 185 | 235 | 5 |
| INITIAL_STOP_TOUCHED_TRADES | 273 | 342 | 143 |
| TARGET_AND_INITIAL_STOP_SAME_BAR_TRADES | 0 | 1 | 0 |
| NEITHER_FIXED_LEVEL_TOUCHED_TRADES | 185 | 289 | 247 |

**Note:** Touch counts may overlap — a trade can touch both target and stop across different bars. They do NOT necessarily sum to TOTAL_TRADES.

### 5.2 Bar-Level Event Counts

| Metric | baseline | donchian | bollinger |
|---|---|---|---|
| target_touch_bar_events | 329 | 429 | 5 |
| initial_stop_touch_bar_events | 413 | 597 | 255 |
| same_bar_ambiguous_bar_events | 0 | 1 | 0 |

### 5.3 Key Observations

1. **baseline**: 273 of 634 trades (43.1%) have fixed initial-stop level touched in post-entry bars up to and including the exit bar; 185 trades (29.2%) touch the target. 185 trades touch neither fixed level.
2. **donchian**: 342 of 841 trades (40.7%) have fixed initial-stop level touched; 235 trades (27.9%) touch the target. Only 1 same-bar ambiguous event.
3. **bollinger**: 143 of 394 trades (36.3%) have fixed initial-stop level touched; only 5 trades (1.3%) touch the target — consistent with short holding periods.
4. **Same-bar fixed-level ambiguities** were rare in this DEVELOPMENT dataset.

---

## 6. Comparison with Phase 21R (Descriptive Only)

| Metric | Phase 21R baseline | Phase 22B baseline | Phase 21R donchian | Phase 22B donchian | Phase 21R bollinger | Phase 22B bollinger |
|---|---|---|---|---|---|---|
| Trade Count | 634 | 634 | 1086 | 841 | 460 | 394 |
| Net PnL | -25.48 | -23.08 | -45.27 | -28.00 | -20.43 | -16.96 |

```
POPULATIONS_DIRECTLY_COMPARABLE = NO
```

**Reason:** Real SL/TP materially changes the trade trajectory. Positions exit earlier via stops, freeing capital for re-entry, which increases trade count. The risk management profile is fundamentally different.

---

## 7. Validations

```
ENGINE_RESULTS_UNCHANGED = YES
INITIAL_STOP_IDENTITY = PASS
ENTRY_BAR_EXCLUDED = YES
FIXED_LEVEL_TOUCH_AUDIT = PASS
COUNTS_ARE_UNIQUE_TRADES = YES
RUNTIME_CHANGED = NO
HOLDOUT_STATE = PRISTINE
```

---

## 8. Safety

```
REAL_WALK_FORWARD_READS = 0
FINAL_HOLDOUT_READS = 0
FINAL_HOLDOUT_EXECUTIONS = 0
HOLDOUT_STATE = PRISTINE
RUNTIME_CHANGED = NO
```

---

## 9. Evidence Artifacts

| File | Description |
|---|---|
| `phase22b_atr_exit_experiment.py` | Experiment script (self-contained, reproducible) |
| `atr-exit-trades.csv` | Per-trade ledger (1869 rows) with entry/exit prices, ATR, stop/target, PnL |
| `atr-exit-summary.json` | Structured summary with per-strategy stats, exit analysis, touch audit |
| `intrabar-touch-analysis.csv` | Fixed-level intrabar touch audit per trade (1869 rows) |

---

## 10. Conclusion

```
PHASE_22B_COMPLETE = YES
ATR_CANONICAL = YES
ATR_PERIOD = 14
STOP_MULTIPLIER = 2.0
TARGET_R_MULTIPLE = 2.0
TRAILING_MULTIPLIER = 3.0

BASELINE_TRADES = 634
BASELINE_SL = 324
BASELINE_TP = 155
BASELINE_TRAILING = 62
BASELINE_STRATEGY_EXIT = 93

DONCHIAN_TRADES = 841
DONCHIAN_SL = 326
DONCHIAN_TP = 199
DONCHIAN_TRAILING = 36
DONCHIAN_STRATEGY_EXIT = 280

BOLLINGER_TRADES = 394
BOLLINGER_SL = 116
BOLLINGER_TP = 2
BOLLINGER_TRAILING = 0
BOLLINGER_STRATEGY_EXIT = 276

TOTAL_TRADES = 1869

ENGINE_RESULTS_UNCHANGED = YES
INITIAL_STOP_IDENTITY = PASS
ENTRY_BAR_EXCLUDED = YES
FIXED_LEVEL_TOUCH_AUDIT = PASS
COUNTS_ARE_UNIQUE_TRADES = YES
RUNTIME_CHANGED = NO
HOLDOUT_STATE = PRISTINE
```

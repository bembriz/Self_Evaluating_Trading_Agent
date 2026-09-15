# Phase 21R — Closure Document (Corrected)

> **Status:** CLOSED
> **Date:** 2026-09-15
> **Role:** Trading Systems Audit / Evidence Engineer
> **Correction:** Phase 21R-I1 — exit reason provenance + position sizing semantics

---

## 1. Canonical Source

```
CANONICAL_BRANCH    = main
CANONICAL_COMMIT    = d2ea5afb4b19976711ab80068b1578505694a902
DATASET_ID          = BYBIT_ETHBTC_V001
DATASET_FINGERPRINT = f561207c018d0f4ade1afdaca3d349a53faec49d732bb5f50933db64e2cbb31d
```

## 2. lenovosrv Integrity Result

No remote actions performed. All evidence generated locally. lenovosrv state unchanged.

## 3. Phase 16b Accounting Recovery

Phase 16b identified and corrected the double-subtraction of slippage in `net_pnl` accounting. The corrected formula is:

```
net_pnl_corrected = gross_pnl_exec - fees
```

The runtime `net_pnl` field uses `gross_pnl_exec - fees - slippage` (double-subtracts). This is a known accounting regression preserved for backwards compatibility. All authoritative ledgers use `net_pnl_corrected`.

## 4. Daily-Loss Recovery

The daily-loss gate (`max_daily_loss = 0.02 × capital = $20`) accumulates realized PnL across UTC days without reset. Once cumulative realized losses reach ~$20, the gate remains permanently active.

**Causality classification:**

| Effect | Classification |
|---|---|
| DAILY_RESET_CAUSAL_EFFECT | PRIMARY |
| DOUBLE_SLIPPAGE_CAUSAL_EFFECT | SECONDARY |
| BUY_ONLY_ORDERING_EFFECT | MINOR |
| HISTORICAL_LOCK_CAUSALITY | STRONGLY_SUPPORTED |

The historical ~403-406 trade cutoff per strategy is explained by the daily-loss gate locking after cumulative realized losses reached ~$20 (2% × $1000 configured capital). Double-slippage accelerated reaching the threshold but was not the primary cause.

## 5. Phase 16c Convergence

Phase 16c addressed convergence issues in paper trading certification. All strategies reached economic steady state within the development split.

## 6. Harness Guards

- `REAL_WALK_FORWARD_READS = 0`
- `FINAL_HOLDOUT_READS = 0`
- `FINAL_HOLDOUT_EXECUTIONS = 0`
- `HOLDOUT_STATE = PRISTINE`
- No certification actions performed
- No remote actions performed

## 7. Canonical Main

```
CANONICAL_MAIN = d2ea5afb4b19976711ab80068b1578505694a902
```

## 8. Authoritative Replay

### Authoritative Results

| Strategy | Trades | Gross Ref PnL | Slippage | Gross Exec PnL | Fees | Net PnL | Viability |
|---|---|---|---|---|---|---|---|
| BASELINE | 634 | +4.957389 | 5.072991 | -0.115603 | 25.364956 | -25.480559 | FAIL |
| DONCHIAN | 1086 | +6.863966 | 8.689373 | -1.825407 | 43.446863 | -45.272269 | FAIL |
| BOLLINGER | 460 | +1.652245 | 3.680330 | -2.028086 | 18.401652 | -20.429737 | FAIL |

Source: `docs/phases/21R/evidence/authoritative-replay-evidence.json`

### Diagnostic Local Replay (NON_AUTHORITATIVE)

| Strategy | Trades | Gross Ref PnL | Gross Exec PnL | Fees | Slippage | Net Corrected |
|---|---|---|---|---|---|---|
| baseline-v1 | 392 | +1.735067 | -1.401280 | 15.681735 | 3.136347 | -17.083014 |
| EthDonchianBreakout-v1 | 482 | +6.975832 | +3.118437 | 19.286974 | 3.857395 | -16.168537 |
| EthBollingerMeanReversion-v1 | 394 | +1.956231 | -1.196160 | 15.761956 | 3.152391 | -16.958115 |

**NON_AUTHORITATIVE_DIAGNOSTIC** — uses `RiskConfig()` defaults which differ from the original experiment configurations. Different trade population. Not used for certification.

## 9. Human-Auditable Ledger Validation

### Trade-Level Reconciliation

```
TRADE_LEVEL_RECONCILIATION = PASS
```

### Account-Level Reconciliation

```
ACCOUNT_LEVEL_RECONCILIATION = PASS
```

### Manual Hand Check

```
MANUAL_HAND_CHECK = PASS
```

## 10. Position Sizing Semantics

### Three Quantities (from `src/domain/risk/sizing.py`)

**1. BUDGET / CASH ALLOCATION**

```
BUDGET_USDT_FORMULA = config.capital * risk_budget_pct(intensity) * drawdown_scale
```

With defaults (MEDIUM, no drawdown): `1000 * 0.01 * 1.0 = $10`

**2. ORDER QUANTITY**

```
ORDER_QUANTITY_FORMULA = budget_usdt / (stop_atr_multiplier * ATR)
```

With defaults: `10 / (2.0 * ATR) = 5 / ATR`

**3. FINAL REFERENCE NOTIONAL**

```
REFERENCE_NOTIONAL_FORMULA = min(quantity * reference_price, max_position_allocation * config.capital)
```

Capped at: `min(0.02 * 1000, 1000 * 1.0) = $20`

### Parameters (from `src/domain/risk/config.py`)

```
capital                    = 1000.0  (fixed, configured)
max_position_allocation    = 0.02    (2% of capital)
stop_atr_multiplier        = 2.0
low_risk_pct               = 0.005
medium_risk_pct            = 0.01
high_risk_pct              = 0.02
leverage                   = 0.0
```

### Representative Trade Values

| Parameter | Value |
|---|---|
| configured_capital | 1000.0 |
| budget_pct (MEDIUM) | 0.01 |
| drawdown_scale | 1.0 |
| ATR (representative) | ~20 |
| stop_atr_multiplier | 2.0 |
| budget_usdt | 10.0 |
| stop_distance | 40.0 |
| quantity (uncapped) | 0.25 |
| reference_price | ~1635 |
| notional (uncapped) | ~408.75 |
| max_notional (cap) | 20.0 |
| **quantity (capped)** | **0.01223** |
| **notional (capped)** | **20.0** |

### $20 Notional Cause

```
TWENTY_DOLLAR_NOTIONAL_CAUSE = B
```

The $20 comes from **B: a risk budget converted through ATR/stop distance and then capped at $20 notional**. The uncapped notional (~$408.75) far exceeds the cap ($20), so every trade hits the cap. The cap is `max_position_allocation * capital = 0.02 * 1000 = $20`.

### Classification

```
POSITION_SIZING_CLASSIFICATION = CAPPED_ALLOCATION_NOTIONAL
```

Not "2% of configured capital" directly — the $20 is the result of a risk-budget calculation that always exceeds the cap. Not "capital-at-risk-with-stop" — the stop distance determines quantity but the actual loss at stop is much less than 2% of capital.

### Capital-at-Risk Test

```
STOP_DISTANCE_USED_FOR_POSITION_QUANTITY = YES
```

The stop distance is used in the denominator: `quantity = budget_usdt / stop_distance`.

```
POSITION_LOSS_AT_STOP_USDT = 0.4892
POSITION_LOSS_AT_STOP_PCT  = 0.049%
TRUE_2_PERCENT_CAPITAL_AT_RISK = NO
```

Calculation: `quantity * stop_distance = 0.01223 * 40 = 0.4892`. As percentage of capital: `0.4892 / 1000 = 0.049%`. This is NOT 2% of capital. The stop distance is used to compute quantity, but the notional cap ($20) means the actual position is much smaller than what the risk budget would produce without the cap.

### Key Properties

```
DOES_ORDER_SIZE_CHANGE_AS_EQUITY_CHANGES = NO
```

Uses `config.capital` (fixed $1000), not dynamic portfolio equity. Position size is invariant to equity changes.

## 11. Exit Reason Distribution

### Status

```
EXIT_REASON_USED_NON_AUTHORITATIVE_LEDGER = YES
```

Previous Phase 21R-I exit reason counts (392/482/394) were generated from `generate-ledger-21r.py` which ran strategies on the DEVELOPMENT split using `RiskConfig()` defaults. This produced a different trade population than the authoritative counts (634/1086/460).

**Previous exit counts are INVALID_FOR_AUTHORITATIVE_CLOSURE.**

### Why Counts Differ

| Population | Baseline | Donchian | Bollinger |
|---|---|---|---|
| Authoritative | 634 | 1086 | 460 |
| Diagnostic (21R-I) | 392 | 482 | 394 |

The diagnostic run used `RiskConfig()` defaults (capital=1000, max_position_allocation=0.02) which produce different trade counts than the original experiment configurations used for the authoritative replay.

### Exit Reasons (Diagnostic Only, NON_AUTHORITATIVE)

Captured from `PaperEvent.exit_reason` during diagnostic replay.

**baseline-v1 (392 trades, NON_AUTHORITATIVE):**

| Exit Reason | Count |
|---|---|
| stop_loss | 194 |
| take_profit | 94 |
| llm_sell | 67 |
| trailing_stop | 37 |

**EthDonchianBreakout-v1 (482 trades, NON_AUTHORITATIVE):**

| Exit Reason | Count |
|---|---|
| stop_loss | 191 |
| llm_sell | 157 |
| take_profit | 115 |
| trailing_stop | 19 |

**EthBollingerMeanReversion-v1 (394 trades, NON_AUTHORITATIVE):**

| Exit Reason | Count |
|---|---|
| llm_sell | 276 |
| stop_loss | 116 |
| take_profit | 2 |
| trailing_stop | 0 |

### LLM_SELL_LABEL_SEMANTICS

```
LLM_SELL_LABEL_SEMANTICS = LEGACY_NAME_ONLY
```

The `llm_sell` exit reason is a string literal set by `PaperEngine.on_price` when `decision.action is Action.SELL` and a position exists. For deterministic strategies (baseline EMA/RSI, Donchian, Bollinger), this is a legacy name — no LLM is involved. The signal comes from pure domain logic (`on_candle()` methods). The label is semantically accurate only for the LLM Decision Agent path (Phase 08).

### Authoritative Exit Reasons

Exit reasons for the authoritative trade population (634/1086/460) require a replay with the exact authoritative configuration. This was not performed in Phase 21R-I1. Exit reasons remain UNKNOWN for the authoritative population.

## 12. Transaction-Cost Economics (Authoritative)

### Per-Strategy Breakdown

| Strategy | Trades | Total Fees | Total Slippage | Gross Ref PnL | Net PnL |
|---|---|---|---|---|---|
| BASELINE | 634 | 25.364956 | 5.072991 | +4.957389 | -25.480559 |
| DONCHIAN | 1086 | 43.446863 | 8.689373 | +6.863966 | -45.272269 |
| BOLLINGER | 460 | 18.401652 | 3.680330 | +1.652245 | -20.429737 |

### Break-Even Threshold

```
FEE_ROUND_TRIP_BPS                    = 20.0  (10 bps entry + 10 bps exit)
SLIPPAGE_ROUND_TRIP_BPS               =  4.0  (2 bps entry + 2 bps exit)
TOTAL_REFERENCE_TO_NET_BREAK_EVEN_BPS = 24.0  (fee + slippage round-trip)
```

A round-trip trade must generate >= 24 bps of reference-price gross PnL to break even after all execution costs.

## 13. Absolute Viability

```
BASELINE_ABSOLUTE_VIABILITY   = FAIL
DONCHIAN_ABSOLUTE_VIABILITY   = FAIL
BOLLINGER_ABSOLUTE_VIABILITY  = FAIL
```

All three strategies show positive raw reference-price PnL (alpha before costs), but transaction costs (fees + slippage) overwhelm the edge:

| Strategy | Raw Alpha (Ref PnL) | After Slippage | After All Costs |
|---|---|---|---|
| BASELINE | +4.96 | -0.12 | -25.48 |
| DONCHIAN | +6.86 | -1.83 | -45.27 |
| BOLLINGER | +1.65 | -2.03 | -20.43 |

## 14. Holdout Status

```
FINAL_HOLDOUT_STATE = PRISTINE
FINAL_HOLDOUT_READS = 0
FINAL_HOLDOUT_EXECUTIONS = 0
```

No holdout data has been accessed. Dataset integrity preserved.

## 15. Certification Status

```
CERTIFICATION_RESTART_REQUIRED = NO
LENOVOSRV_ACTION_REQUIRED = NO
```

Phase 21R is definitively closed. No further certification actions are required. The economic conclusion (FAIL on all strategies) is clear and does not require additional validation.

## 16. Next Authorized Research Direction

```
PHASE_22_RECOMMENDED_SCOPE = Execution Economics
```

### Recommended Investigation

- **Venue type:** Spot vs USDT Perpetual
- **Direction:** Long-only first
- **Order type:** Taker vs Maker/Post-only
- **Fee burden:** Quantify impact of different fee tiers
- **Slippage burden:** Model realistic slippage for ETHBTC
- **Funding:** Perpetual funding rate impact
- **Mark price:** Mark price vs last price divergence
- **Liquidation/margin:** Margin requirements for perpetuals
- **Signals:** Same alpha signals (no strategy tuning initially)

### Rationale

All three strategies show positive raw reference-price PnL, but transaction costs overwhelm the edge. The next logical step is to reduce execution costs through venue/order-type optimization before tuning the alpha signals themselves.

---

## Appendix A: Ledger Precision Audit

```
CSV_DECIMAL_PRECISION         = 16 significant digits
CSV_MAX_RECONCILIATION_ERROR  = 6.94e-18
CSV_RECONCILIATION_TOLERANCE  = 0.000001
CSV_RECONCILIATION            = PASS
LEDGER_PRECISION_CHANGE_REQUIRED = NO
LEDGER_PRECISION_AFTER        = 16 significant digits (sufficient)
```

## Appendix B: Artifact Manifest

| File | SHA256 | Status |
|---|---|---|
| `evidence/authoritative-replay-evidence.json` | (new) | AUTHORITATIVE |
| `evidence/generate-ledger-21r.py` | `af8a93d3...` | NON_AUTHORITATIVE_DIAGNOSTIC |
| `evidence/diagnostic-trade-ledger-21r.csv` | `5b84e1c5...` | NON_AUTHORITATIVE_DIAGNOSTIC |
| `evidence/economics-summary-21r.json` | `dbd0b6dd...` | NON_AUTHORITATIVE_DIAGNOSTIC |
| `phase-21r-closure.md` | (updated) | AUTHORITATIVE |
| `../21/evidence/diagnostic-trade-ledger.csv` | `9c1b42ed...` | SUPERSEDED |
| `../21/evidence/economics-summary.json` | `ead2637c...` | SUPERSEDED |
| `../21/evidence/economics-summary.md` | `10698237...` | SUPERSEDED |

## Appendix C: Safety Verification

```
REAL_WALK_FORWARD_READS     = 0
FINAL_HOLDOUT_READS         = 0
FINAL_HOLDOUT_EXECUTIONS    = 0
HOLDOUT_STATE               = PRISTINE
REMOTE_ACTIONS              = NONE
CERTIFICATION_ACTIONS       = NONE
```

---

```
PHASE_21R_STATUS = CLOSED
CANONICAL_MAIN   = d2ea5afb4b19976711ab80068b1578505694a902
```

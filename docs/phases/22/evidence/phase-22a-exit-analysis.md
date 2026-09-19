# Phase 22-A — Exit Reason Analysis (Authoritative Population)

> **Status:** COMPLETE
> **Date:** 2026-09-16
> **Role:** Trading Systems Audit / Evidence Engineer
> **Correction:** Phase 22-A-I1 — exit reason semantics corrected

---

## 1. Authoritative Population Verification

| Strategy | Expected Trades | Actual Trades | Match |
|---|---|---|---|
| baseline | 634 | 634 | PASS |
| donchian | 1086 | 1086 | PASS |
| bollinger | 460 | 460 | PASS |

**Configuration Used:**
```python
RiskConfig(stop_loss_required=False, version="risk-v1-nostop-mvp-a")
```

**Key Implementation Detail:**
The authoritative replay uses `atr=None` (not computed ATR), matching the `LabSessionRunner` behavior. This causes:
- ATR to be 0.0 internally
- ATR-based stop/TP/trailing were not active in this authoritative replay
- Only `FALLBACK_NEAR_ENTRY_STOP` and `STRATEGY_SIGNAL_EXIT` occur

---

## 2. Exit Semantics Configuration

```
REAL_STOP_LOSS_CONFIGURED      = NO
REAL_STOP_LOSS_HITS            = NOT_APPLICABLE
TAKE_PROFIT_CONFIGURED         = NO
TAKE_PROFIT_HITS               = NOT_APPLICABLE
TRAILING_STOP_AVAILABLE        = NO
PAPER_ENGINE_NONE_STOP_FALLBACK_DETECTED = YES
```

### Exit Reason Label Mapping

| Raw Label | Corrected Label | Semantics |
|---|---|---|
| `stop_loss` | `FALLBACK_NEAR_ENTRY_STOP` | PaperEngine fallback when `atr=None`: stop set to `price * (1 - 1e-9)` ≈ entry price |
| `llm_sell` | `STRATEGY_SIGNAL_EXIT` | Strategy logic (EMA/RSI, Donchian, Bollinger) triggered SELL; legacy `llm_sell` label |

---

## 3. Exit Reason Distribution (Corrected)

### baseline (634 trades)

| Exit Reason | Count | Rate | Avg Net PnL | Total Net PnL | Avg Holding (bars) | Avg Return (bps) |
|---|---|---|---|---|---|---|
| FALLBACK_NEAR_ENTRY_STOP | 580 | 91.48% | -0.084443 | -48.977073 | 4.3 | -18.24 |
| STRATEGY_SIGNAL_EXIT | 54 | 8.52% | +0.435121 | +23.496514 | 50.7 | +241.85 |
| TAKE_PROFIT | 0 | 0.00% | — | — | — | — |
| TRAILING_STOP | 0 | 0.00% | — | — | — | — |

### donchian (1086 trades)

| Exit Reason | Count | Rate | Avg Net PnL | Total Net PnL | Avg Holding (bars) | Avg Return (bps) |
|---|---|---|---|---|---|---|
| FALLBACK_NEAR_ENTRY_STOP | 951 | 87.57% | -0.094716 | -90.074446 | 2.7 | -23.39 |
| STRATEGY_SIGNAL_EXIT | 135 | 12.43% | +0.331868 | +44.802176 | 38.3 | +190.16 |
| TAKE_PROFIT | 0 | 0.00% | — | — | — | — |
| TRAILING_STOP | 0 | 0.00% | — | — | — | — |

### bollinger (460 trades)

| Exit Reason | Count | Rate | Avg Net PnL | Total Net PnL | Avg Holding (bars) | Avg Return (bps) |
|---|---|---|---|---|---|---|
| FALLBACK_NEAR_ENTRY_STOP | 339 | 73.70% | -0.088535 | -30.013311 | 1.7 | -20.29 |
| STRATEGY_SIGNAL_EXIT | 121 | 26.30% | +0.079203 | +9.583573 | 3.7 | +63.68 |
| TAKE_PROFIT | 0 | 0.00% | — | — | — | — |
| TRAILING_STOP | 0 | 0.00% | — | — | — | — |

---

## 4. Key Findings

### 4.1 Fallback Near-Entry Stop Mechanism

When `atr=None`, the PaperEngine's RiskEngine cannot compute ATR-based stops. The fallback sets stop to `price * (1 - 1e-9)` ≈ entry price. This causes:
- Positions exit almost immediately when price dips even slightly
- Short holding periods (1-4 bars median)
- High exit rate (73-91% of trades)

### 4.2 ATR-Based Features Inactive

With `atr=None` in this authoritative replay:
- **Take profit:** Not configured (risk engine requires ATR for target calculation)
- **Trailing stop:** Not available (update_trailing requires ATR > 0)
- **Real stop loss:** Not configured (stop_loss_required=False)

### 4.3 Strategy Signal Performance

`STRATEGY_SIGNAL_EXIT` trades are consistently profitable:
- baseline: +23.50 total net PnL (win rate 98.15%)
- donchian: +44.80 total net PnL (win rate 83.70%)
- bollinger: +9.58 total net PnL (win rate 89.26%)

However, these gains are overwhelmed by fallback near-entry stop losses.

---

## 5. Evidence Artifacts

| File | Description |
|---|---|
| `capture-authoritative-exit-reasons.py` | Script that captures exit reasons using exact authoritative config |
| `authoritative-exit-reasons.csv` | Full trade ledger with exit reasons (2180 rows) |
| `exit-reason-analysis.json` | Structured analysis with all metrics |
| `exit-reason-analysis.csv` | Summary CSV with exit reason counts, rates, and PnL |
| `generate-exit-reason-csv.py` | Script that generates the summary CSV |

---

## 6. Conclusion

```
EXIT_REASON_DATA_AUTHORITATIVE = YES
EXIT_SEMANTICS_CORRECTED       = YES
```

Exit reasons are now available for the authoritative trade population (634/1086/460) with corrected semantics. The data was captured using the exact authoritative configuration:
- `RiskConfig(stop_loss_required=False, version="risk-v1-nostop-mvp-a")`
- `atr=None` (matching LabSessionRunner behavior)

The exit reason distribution is deterministic and reproducible. The trade counts match the authoritative replay evidence exactly.

---

## 7. Implications for Phase 22

The exit reason analysis reveals:

1. **Fallback near-entry stop dominates exits** (73-91%) due to `atr=None` configuration
2. **ATR-based stop/TP/trailing were not active** in this authoritative replay
3. **Strategy signal exits** are profitable but minority (9-26% of exits)

The authoritative configuration produces a trade population where risk management features (stops, TP, trailing) are inactive. Exit behavior is governed by PaperEngine's fallback mechanism, not by configured risk parameters.

---

```
PHASE_22A_STATUS = COMPLETE
AUTHORITATIVE_POPULATION = VERIFIED
EXIT_REASON_DATA = CAPTURED
EXIT_SEMANTICS = CORRECTED
```

# Absolute Viability Gate — Design (Phase 19C)

Design-only phase. No code, no staging, no commit, no economic evaluation, no
walk-forward, no holdout. This document defines a **prospective** two-stage
research gate and its compatibility with the Phase 17G promotion machine. It does
not rewrite any historical result.

## Context

- Base commit: `7ea8b2c` (19B committed).
- `PHASE_19B_CLOSED=YES`; `HOLDOUT_STATE=PRISTINE`.

## Problem Discovered In 19B

Phase 19B evaluated `EthDonchianBreakout-v1` against `baseline-v1` on full
DEVELOPMENT. Under the predeclared **relative** rule it obtained:

- `DEVELOPMENT_RESULT=IMPROVED` (expectancy, profit factor and net PnL all
  improved relative to baseline; drawdown within the material threshold).

Yet its **absolute** economics remained negative:

- `DONCHIAN_NET_PNL=-20.008372225067937` (< 0)
- `DONCHIAN_PROFIT_FACTOR=0.4222390254700682` (< 1)
- `DONCHIAN_EXPECTANCY=-0.04928170498785207` (< 0)

Therefore "better than baseline" must **not** automatically mean "worth spending
WALK_FORWARD". The human gate recorded `ABSOLUTE_VIABILITY_GATE=FAIL` and
`WALK_FORWARD_AUTHORIZED=NO` for 19B. This design formalizes that check.

## Scope

- Applies to future Strategy Lab candidates, prospectively.
- DEVELOPMENT-level economic gate; independent of BTC context, LLM or any
  specific strategy family.
- No composite score, no ranking, no optimization objective.
- Does not change the Phase 18B/18D/19B classification rule and does not touch
  historical evidence.

## Two-Stage Policy

### Stage 1 — Relative Quality (unchanged)

The existing predeclared rule is preserved exactly:

```
DEVELOPMENT_RESULT ∈ {IMPROVED, MIXED, NOT_IMPROVED}
```

A candidate may continue only if `DEVELOPMENT_RESULT == IMPROVED`. `MIXED` and
`NOT_IMPROVED` stop the candidate for that phase.

### Stage 2 — Absolute Viability (new, prospective)

Require all three, evaluated on the same DEVELOPMENT run and the same economic
conditions as Stage 1:

```
NET_PNL        > 0
EXPECTANCY     > 0
PROFIT_FACTOR  > 1.0
```

If all three pass: `ABSOLUTE_VIABILITY_GATE=PASS`. Otherwise:
`ABSOLUTE_VIABILITY_GATE=FAIL`.

## Exact Boolean Semantics

Let `net_pnl`, `expectancy`, `profit_factor` be the candidate's DEVELOPMENT
metrics produced by the existing metric implementation (no new formulas):

```
NET_PNL_GT_0        = is_finite(net_pnl)        AND net_pnl        > 0
EXPECTANCY_GT_0     = is_finite(expectancy)     AND expectancy     > 0
PROFIT_FACTOR_GT_1  = is_finite(profit_factor)  AND profit_factor  > 1.0

ABSOLUTE_VIABILITY_GATE = PASS  iff  NET_PNL_GT_0 AND EXPECTANCY_GT_0 AND PROFIT_FACTOR_GT_1
                          else   FAIL
```

- Strict inequalities only; equality fails (`net_pnl == 0`, `expectancy == 0`,
  `profit_factor == 1.0` → FAIL).
- Boolean combination only; no weighting, no normalization, no threshold
  beyond the three above.

## Fail-Closed Behavior

The gate is fail-closed. `ABSOLUTE_VIABILITY_GATE=FAIL` whenever any required
metric is:

- missing / not present in the metrics mapping;
- `None` (undefined, e.g. no closed trades);
- `NaN`;
- non-finite (`+inf` / `-inf`).

Consequences:

- `profit_factor == inf` (no losing trades) is **non-finite** and therefore
  FAILS. The gate never infers PASS from an undefined or limit value.
- An empty or all-undefined metric set cannot pass.
- No default, forward-fill, or imputation is applied to missing metrics.

## Walk-Forward Eligibility

For future candidates:

```
WALK_FORWARD_ELIGIBLE = YES  iff
    DEVELOPMENT_RESULT == IMPROVED
    AND
    ABSOLUTE_VIABILITY_GATE == PASS
otherwise NO
```

Distinction that must remain explicit:

- `WALK_FORWARD_ELIGIBLE` — a computed, mechanical property.
- `WALK_FORWARD_AUTHORIZED` — a human decision; required even when eligible.

`WALK_FORWARD_ELIGIBLE=YES` does **not** imply `WALK_FORWARD_AUTHORIZED=YES`.
No walk-forward block is consumed without explicit human authorization.

## Prospective-Only Application

- The gate applies to candidates evaluated **after** this design is approved.
- Historical results are immutable and are **not** rewritten, relabeled or
  recomputed:

| Phase | Strategy | Recorded result (preserved) |
|---|---|---|
| 18B | `EmaRsiBtcContext-v1` | `DEVELOPMENT_RESULT=MIXED` |
| 18D | `EmaRsiBtcRegime-v1` | `DEVELOPMENT_RESULT=MIXED` |
| 19B | `EthDonchianBreakout-v1` | `DEVELOPMENT_RESULT=IMPROVED`, `WALK_FORWARD_CANDIDATE=YES`, `ABSOLUTE_VIABILITY_GATE=FAIL`, `WALK_FORWARD_AUTHORIZED=NO` |

- The 19B `ABSOLUTE_VIABILITY_GATE=FAIL` was a **human** record; it is not
  retroactively inserted into the 19B evidence files. Future phases record the
  gate mechanically from the start.

## Compatibility With Phase 17G

Existing promotion machine (`src/lab/promote.py`), states unchanged:

```
DRAFT → PARITY_PASSED → ROBUSTNESS_PASSED → HOLDOUT_READY
```

- `advance_to_parity` requires `ParityEvidence(runtime_parity,
  double_run_reproducibility)`.
- `advance_to_robustness` requires `RobustnessEvidence(...)` derived from
  **walk-forward**, and is therefore **after** walk-forward has been consumed.
- `advance_to_holdout_ready` requires `HoldoutReadinessEvidence(...)` and does
  not consume the holdout.

**`ParityEvidence` semantics are preserved unchanged.** `PARITY_PASSED` means
"runtime parity + reproducibility passed" and nothing about economics. A strategy
may legitimately be:

```
PARITY_PASSED
ABSOLUTE_VIABILITY_GATE=FAIL
WALK_FORWARD_ELIGIBLE=NO
```

The absolute viability gate is **not** attached to `ParityEvidence` and the
`DRAFT → PARITY_PASSED` transition does **not** depend on economic viability.

### Pre-Walk-Forward Guard (not a PromotionState)

The absolute gate is enforced through a separate mechanical eligibility rule:

```
WALK_FORWARD_ELIGIBLE = YES  iff
    DEVELOPMENT_RESULT == IMPROVED
    AND
    ABSOLUTE_VIABILITY_GATE == PASS
otherwise NO
```

This is a **pre-walk-forward policy guard / evidence condition**, not a new
`PromotionState`. It complements the existing state machine; it does not extend
it.

### Enforcement Point

The guard must be enforced **before any WALK_FORWARD dataset adapter is
opened, read or iterated**. The conceptual order is:

1. DEVELOPMENT evaluation complete.
2. Parity/reproducibility complete (`ParityEvidence`, unchanged).
3. Compute `AbsoluteViabilityEvidence`.
4. Compute `WALK_FORWARD_ELIGIBLE` via
   `walk_forward_eligible(development_result, absolute_viability)`.
5. Require explicit **HUMAN** authorization.
6. Only then permit WALK_FORWARD access.

Failing eligibility must result in `WALK_FORWARD_READS=0` (no adapter is ever
opened). Eligibility never substitutes for human authorization.

### Minimum Change Required (later, not in 19C)

Preferred minimal additions, reusing the existing state machine:

1. Add one frozen evidence dataclass `AbsoluteViabilityEvidence` with the three
   required metrics (`net_pnl`, `expectancy`, `profit_factor`), whose `passed`
   property implements the exact boolean semantics and fail-closed rules above.
2. Add a pure helper `walk_forward_eligible(development_result,
   absolute_viability) -> bool` implementing the eligibility rule.

Do **not** create an `ABSOLUTE_VIABILITY_PASSED` state, a `WALK_FORWARD_READY`
state, or any new state-machine framework. Do **not** modify `ParityEvidence`
semantics.

Considered and rejected:

- Attaching `AbsoluteViabilityEvidence` to `ParityEvidence` / making
  `DRAFT → PARITY_PASSED` depend on economics: conflates runtime parity with
  economic viability; rejected.
- Adding a new state: unnecessary; the guard is a boolean condition, not a
  lifecycle stage.
- Checking only at `advance_to_robustness`: too late; walk-forward would already
  have been consumed.

## Tests Required For Later Implementation

Gate predicate:

1. PASS only when all three are strictly satisfied.
2. FAIL when `net_pnl == 0`, `expectancy == 0`, or `profit_factor == 1.0`.
3. FAIL when any metric is `None`.
4. FAIL when any metric is `NaN` or non-finite (`inf`), including
   `profit_factor == inf`.
5. FAIL when a required metric key is missing.
6. Deterministic and side-effect free.

Eligibility truth table and guard:

7. `IMPROVED` + `PASS` → `WALK_FORWARD_ELIGIBLE=YES`.
8. `IMPROVED` + `FAIL` → `NO`.
9. `MIXED` + `PASS` → `NO`.
10. `NOT_IMPROVED` + `PASS` → `NO`.
11. `ABSOLUTE_VIABILITY_GATE=FAIL` ⇒ `WALK_FORWARD_ELIGIBLE=NO`.
12. Eligibility `YES` still requires human authorization
    (`WALK_FORWARD_ELIGIBLE` never implies `WALK_FORWARD_AUTHORIZED`).
13. Rejected eligibility performs ZERO walk-forward reads (no adapter opened,
    read or iterated).
14. `walk_forward_eligible(...)` is pure and deterministic.

Promotion compatibility:

15. `PARITY_PASSED` can coexist with `ABSOLUTE_VIABILITY_GATE=FAIL`
    (`ParityEvidence` semantics unchanged; `DRAFT → PARITY_PASSED` is not
    affected by economics).
16. Existing 17G parity behavior remains unchanged; no new promotion states are
    introduced and `request_post_mvp_a` behavior is unchanged.
17. Historical evidence files (18B/18D/19B) are not modified by the
    implementation.

## Migration / Non-Migration

- **Non-migration:** no historical artifact is recomputed, relabeled or
  rewritten; existing SpecIds, registry entries and evidence JSON/MD remain
  byte-identical.
- **Forward-only:** future candidates record `ABSOLUTE_VIABILITY_GATE` and
  `WALK_FORWARD_ELIGIBLE` mechanically in their evaluation evidence.
- The 19B `WALK_FORWARD_CANDIDATE=YES` remains a valid relative-stage record; it
  is not contradicted, only complemented by the separate absolute gate.

## Non-Goals

- No new score, weighted metric, composite index, ranking or optimization.
- No change to the relative classification rule.
- No retroactive change to any historical experiment.
- No new promotion state-machine architecture.
- No code, economic evaluation, walk-forward or holdout in 19C.

## Evidence And Gate

Deliverable is this design document only, at
`docs/superpowers/specs/2026-09-12-absolute-viability-gate-design.md`. Keep the
working tree otherwise unchanged: no staging, no commit, no push, no
walk-forward, no holdout. Stop at `READY_FOR_HUMAN_PHASE_19C_DESIGN_GATE`.

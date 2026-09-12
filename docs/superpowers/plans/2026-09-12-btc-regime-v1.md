# EmaRsiBtcRegime-v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Project override:** this repository forbids `git commit`/`git push` without explicit human authorization (AGENTS.md §4.2, §7). The "Commit" steps in the generic template are replaced here by **evidence + staging-prohibited**. Do not stage or commit; stop at `READY_FOR_HUMAN_18C_IMPLEMENTATION_GATE`.

**Goal:** Implement `EmaRsiBtcRegime-v1`, a Strategy Lab candidate that preserves `baseline-v1` ETH behavior and filters BUY signals with a causal BTC trend+slope regime gate.

**Architecture:** A new `src/lab/strategies/ema_rsi_btc_regime.py` composes a fresh `EmaRsiBaseline` and precomputes a causal `BTC_RISK_ON` boolean per aligned BTC candle using the existing `domain.market.indicators.ema`. It reuses `StrategyDefinition`/`strategy_artifact_identity` and the `ExperimentSpec` `primary`/`context` mapping. `LabSessionRunner` and all protected runtime files are unchanged.

**Tech Stack:** Python 3.12, pytest, ruff, mypy (strict), uv.

## Global Constraints

- Rule (verbatim): `BTC_RISK_ON[t] = EMA20[t] > EMA50[t] AND EMA20[t] > EMA20[t-4]`.
- `btc_slope_lookback = 4`; BTC EMA fast/slow = 20/50; ETH baseline params = 20/50/14/80.0.
- `EMA20[t] > EMA20[t-4]` means **positive EMA slope/direction**, never "quantitative acceleration".
- BTC filters BUY only; BTC never creates BUY; BTC never forces SELL; SELL/HOLD preserved exactly.
- Fail closed during warmup/missing context; 1:1 ETH/BTC alignment enforced.
- Reuse existing identity + `ExperimentSpec`; no new fingerprint system; no `LabSessionRunner` change.
- Data safety: DEVELOPMENT only. `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0`, `FINAL_HOLDOUT_EXECUTIONS=0`, `HOLDOUT_STATE=PRISTINE`.
- New module must reach 100% statement and branch coverage. Global coverage ≥ 90%.
- No staging, no commit, no push, no economic evaluation, no walk-forward, no holdout.
- `EmaRsiBaseline` and `EmaRsiBtcContext-v1` are frozen historical artifacts.

---

## File Structure

- Create `src/lab/strategies/ema_rsi_btc_regime.py` — strategy, config, alignment, causal BTC regime, `strategy_definition`.
- Create `harness/scripts/phase18c_development_smoke.py` — DEVELOPMENT-only decision-count smoke.
- Create `tests/lab/test_ema_rsi_btc_regime.py` — unit contract.
- Create `tests/lab/test_phase18c_development_smoke.py` — smoke contract.
- Create `tests/integration/test_ema_rsi_btc_regime_integration.py` — real adapters + runner.
- Create `tests/e2e/test_ema_rsi_btc_regime_e2e.py` — DEVELOPMENT-only chain.
- Create `docs/phases/18C/evidence/` — logs and coverage.

---

### Task 1: `EmaRsiBtcRegime` strategy module + unit tests

**Files:**
- Create: `src/lab/strategies/ema_rsi_btc_regime.py`
- Test: `tests/lab/test_ema_rsi_btc_regime.py`

**Interfaces:**
- Consumes: `EmaRsiBaseline`, `EmaRsiConfig` (`domain.trading.strategy`); `ema` (`domain.market.indicators`); `Signal`, `Action`; `StrategyDefinition` (`lab.fingerprints`); `FrozenDatasetAdapter` (`lab.frozen_dataset`).
- Produces:
  - `EmaRsiBtcRegimeConfig(ema_fast=20, ema_slow=50, rsi_period=14, rsi_exit=80.0, btc_ema_fast=20, btc_ema_slow=50, btc_slope_lookback=4)`
  - `EmaRsiBtcRegime(strategy_name="EmaRsiBtcRegime", version="ema-rsi-btc-regime-v1")`
  - `EmaRsiBtcRegime.from_adapters(*, primary, context, config=None) -> EmaRsiBtcRegime`
  - `EmaRsiBtcRegime.on_candle(candle) -> Signal`
  - `strategy_definition(config=None) -> StrategyDefinition`

**Implementation (`src/lab/strategies/ema_rsi_btc_regime.py`):**

```python
"""EMA/RSI baseline candidate with a causal BTC trend+slope regime gate on ETH BUYs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from domain.market.candle import Candle
from domain.market.indicators import ema
from domain.trading.signal import Action, Signal
from domain.trading.strategy import EmaRsiBaseline, EmaRsiConfig
from lab.fingerprints import StrategyDefinition
from lab.frozen_dataset import FrozenDatasetAdapter


@dataclass(frozen=True, slots=True)
class EmaRsiBtcRegimeConfig:
    """Frozen ETH baseline and BTC trend+slope context parameters."""

    ema_fast: int = 20
    ema_slow: int = 50
    rsi_period: int = 14
    rsi_exit: float = 80.0
    btc_ema_fast: int = 20
    btc_ema_slow: int = 50
    btc_slope_lookback: int = 4


class EmaRsiBtcRegime:
    """Filter baseline ETH BUY candidates with a causal BTC trend+slope regime."""

    strategy_name = "EmaRsiBtcRegime"
    version = "ema-rsi-btc-regime-v1"

    def __init__(
        self,
        *,
        primary_candles: Sequence[Candle],
        btc_candles: Sequence[Candle],
        config: EmaRsiBtcRegimeConfig | None = None,
    ) -> None:
        self._config = config or EmaRsiBtcRegimeConfig()
        periods = (
            self._config.ema_fast,
            self._config.ema_slow,
            self._config.rsi_period,
            self._config.btc_ema_fast,
            self._config.btc_ema_slow,
        )
        if min(periods) <= 0:
            raise ValueError("indicator periods must be positive")
        if self._config.btc_slope_lookback < 1:
            raise ValueError("btc_slope_lookback must be positive")
        if self._config.ema_fast >= self._config.ema_slow:
            raise ValueError("ETH EMA fast period must be less than slow period")
        if self._config.btc_ema_fast >= self._config.btc_ema_slow:
            raise ValueError("BTC EMA fast period must be less than slow period")

        primary = tuple(primary_candles)
        context = tuple(btc_candles)
        if not primary:
            raise ValueError("aligned ETH/BTC candles must be non-empty")
        if len(primary) != len(context):
            raise ValueError("ETH/BTC candle length mismatch")
        for index, (eth_candle, btc_candle) in enumerate(zip(primary, context, strict=True)):
            if eth_candle.timestamp_ms != btc_candle.timestamp_ms:
                raise ValueError(f"ETH/BTC timestamp mismatch at row {index}")

        btc_closes = [candle.close for candle in context]
        btc_fast = ema(btc_closes, self._config.btc_ema_fast)
        btc_slow = ema(btc_closes, self._config.btc_ema_slow)
        lookback = self._config.btc_slope_lookback
        risk_on: list[bool] = []
        for index in range(len(btc_closes)):
            fast = btc_fast[index]
            slow = btc_slow[index]
            lag_index = index - lookback
            lag = btc_fast[lag_index] if lag_index >= 0 else None
            ready = fast is not None and slow is not None and lag is not None
            risk_on.append(bool(ready and fast > slow and fast > lag))
        self._btc_risk_on = tuple(risk_on)
        self._primary = primary
        self._baseline = EmaRsiBaseline(
            EmaRsiConfig(
                ema_fast=self._config.ema_fast,
                ema_slow=self._config.ema_slow,
                rsi_period=self._config.rsi_period,
                rsi_exit=self._config.rsi_exit,
            )
        )
        self._index = 0

    @classmethod
    def from_adapters(
        cls,
        *,
        primary: FrozenDatasetAdapter,
        context: FrozenDatasetAdapter,
        config: EmaRsiBtcRegimeConfig | None = None,
    ) -> EmaRsiBtcRegime:
        """Construct from matching frozen DEVELOPMENT dataset adapters."""
        primary_range = primary.range
        context_range = context.range
        if (
            primary_range.symbol,
            primary_range.timeframe,
            primary_range.row_start,
            primary_range.row_end,
        ) != ("ETHUSDT", "15m", context_range.row_start, context_range.row_end):
            raise ValueError("primary adapter must be aligned ETHUSDT 15m")
        if (
            context_range.dataset_id,
            context_range.symbol,
            context_range.timeframe,
            context_range.manifest_sha,
        ) != (
            primary_range.dataset_id,
            "BTCUSDT",
            "15m",
            primary_range.manifest_sha,
        ):
            raise ValueError("context adapter must be aligned BTCUSDT 15m from same dataset")
        return cls(
            primary_candles=primary.candles,
            btc_candles=context.candles,
            config=config,
        )

    def on_candle(self, candle: Candle) -> Signal:
        """Return baseline signal, filtering only BUY candidates with BTC regime."""
        if self._index >= len(self._primary):
            raise ValueError("preloaded ETH sequence exhausted")
        expected = self._primary[self._index]
        if candle != expected:
            raise ValueError("runner candle does not match preloaded ETH sequence")

        baseline_signal = self._baseline.on_candle(candle)
        risk_on = self._btc_risk_on[self._index]
        self._index += 1
        if baseline_signal.action is not Action.BUY:
            return baseline_signal
        if risk_on:
            return Signal(
                timestamp_ms=baseline_signal.timestamp_ms,
                action=Action.BUY,
                intensity=baseline_signal.intensity,
                reason="ema_cross_up_btc_regime_confirmed",
            )
        return Signal(
            timestamp_ms=baseline_signal.timestamp_ms,
            action=Action.HOLD,
            intensity=baseline_signal.intensity,
            reason="btc_regime_block",
        )


def strategy_definition(
    config: EmaRsiBtcRegimeConfig | None = None,
) -> StrategyDefinition:
    """Declare candidate source/config using the existing identity contract."""
    candidate_config = config or EmaRsiBtcRegimeConfig()
    return StrategyDefinition(
        strategy_id=EmaRsiBtcRegime.strategy_name,
        strategy_version=EmaRsiBtcRegime.version,
        kind="deterministic",
        normalized_config={
            "ema_fast": candidate_config.ema_fast,
            "ema_slow": candidate_config.ema_slow,
            "rsi_period": candidate_config.rsi_period,
            "rsi_exit": candidate_config.rsi_exit,
            "btc_ema_fast": candidate_config.btc_ema_fast,
            "btc_ema_slow": candidate_config.btc_ema_slow,
            "btc_slope_lookback": candidate_config.btc_slope_lookback,
        },
        sources=(
            "lab.strategies.ema_rsi_btc_regime",
            "domain.trading.strategy",
            "domain.market.indicators",
        ),
    )
```

**Unit test contract (`tests/lab/test_ema_rsi_btc_regime.py`)** — mirror the 18A unit suite, adapted to the slope rule. Tests (each must fail first):

1. `test_eth_buy_with_bullish_slope_is_confirmed` — BTC trend up and rising EMA20 → BUY reason `ema_cross_up_btc_regime_confirmed`.
2. `test_eth_buy_with_bearish_slope_is_blocked` — BTC `EMA20 > EMA50` but `EMA20[t] <= EMA20[t-4]` → HOLD reason `btc_regime_block`.
3. `test_eth_buy_with_bearish_trend_is_blocked` — `EMA20 <= EMA50` → HOLD.
4. `test_eth_sell_is_preserved_for_ready_regime` (parametrized bullish/bearish) — SELL reason/intensity unchanged.
5. `test_eth_sell_is_preserved_during_btc_warmup`.
6. `test_eth_hold_is_preserved_exactly`.
7. `test_eth_buy_is_blocked_during_btc_warmup` — EMA50 not ready → HOLD.
8. `test_eth_buy_is_blocked_during_slope_warmup` — EMA20 ready but `EMA20[t-4]` unavailable → HOLD.
9. `test_aligned_timestamps_are_accepted`.
10. `test_empty_or_different_length_sequences_fail_closed`.
11. `test_misaligned_timestamp_fails_closed`.
12. `test_future_btc_changes_do_not_change_past_decisions` — temporal corruption / no-lookahead.
13. `test_same_input_produces_same_decisions`.
14. `test_runner_sequence_must_match_preloaded_eth`.
15. `test_runner_cannot_process_more_than_preloaded_eth`.
16. `test_invalid_period_config_fails_closed` — parametrized `ema_fast=0`, `rsi_period=-1`, `btc_ema_slow=0`, `btc_slope_lookback=0`, `ema_fast==ema_slow`, `btc_ema_fast==btc_ema_slow`.
17. `test_regime_config_changes_existing_strategy_artifact_identity` — changing `btc_slope_lookback` and BTC periods changes identity; sources tuple exact.
18. `test_btc_dataset_or_slice_change_changes_spec_id` — `ExperimentSpec` with `primary`/`context`; context dataset/slice change changes `spec_id`.
19. `test_baseline_defaults_and_non_buy_semantics_remain_intact`.
20. `test_final_holdout_range_remains_blocked_without_reading_it`.

- [ ] **Step 1:** Write `tests/lab/test_ema_rsi_btc_regime.py` (all tests above). Run `uv run pytest tests/lab/test_ema_rsi_btc_regime.py -q` → **RED** (module missing).
- [ ] **Step 2:** Create `src/lab/strategies/ema_rsi_btc_regime.py` exactly as above. Run the same command → **GREEN**.
- [ ] **Step 3:** `uv run pytest tests/lab/test_ema_rsi_btc_regime.py --cov=lab.strategies.ema_rsi_btc_regime --cov-branch --cov-report=term-missing -q` → 100% statements and branches.
- [ ] **Step 4:** Record evidence (no commit).

---

### Task 2: DEVELOPMENT smoke script + test

**Files:**
- Create: `harness/scripts/phase18c_development_smoke.py`
- Test: `tests/lab/test_phase18c_development_smoke.py`

**Interfaces:**
- Consumes: `EmaRsiBtcRegime`, `EmaRsiBtcRegimeConfig`, `EmaRsiBaseline`, `FrozenDatasetAdapter`, `DEVELOPMENT_END`, `is_holdout_range`.
- Produces: `decision_counts(primary_candles, btc_candles, *, config=None) -> dict[str, int]` and `development_smoke(repo_root=REPO_ROOT) -> dict[str, object]`, printing JSON on stdout. Mirrors 18A: counts baseline BUY signals, regime BUY signals, blocked BUYs, verifies `candidate + blocked == baseline`, confirms `BTC_BLOCKED_BUYS > 0` on a small DEVELOPMENT range `[0, 5000)`, reports `FINAL_HOLDOUT_READS=0`.

**Smoke test (`tests/lab/test_phase18c_development_smoke.py`):** run the script via `subprocess` (like 18A), parse JSON, assert `COUNTER_UNIT == "strategy_decisions"`, `BTC_BLOCKED_BUYS > 0`, `FINAL_HOLDOUT_READS == 0`, `FINAL_HOLDOUT_EXECUTIONS == 0`, and the accounting identity.

- [ ] **Step 1:** Write the smoke test. Run it → **RED** (script missing).
- [ ] **Step 2:** Implement `harness/scripts/phase18c_development_smoke.py`. Run test → **GREEN**.
- [ ] **Step 3:** Run the script directly on DEVELOPMENT `[0, 5000)` to capture evidence JSON.
- [ ] **Step 4:** Record evidence (no commit).

---

### Task 3: Integration tests

**Files:**
- Create: `tests/integration/test_ema_rsi_btc_regime_integration.py`

**Interfaces:** real `FrozenDatasetAdapter` + unchanged `LabSessionRunner` + `PaperEngine`.

Tests:
1. `test_aligned_real_adapters_run_through_unchanged_lab_runner` — events align with ETH candles.
2. `test_real_adapter_candidate_is_reproducible` — double run identical `event_trace_hash`/`metrics_hash_value`.
3. `test_adapter_range_mismatch_fails_closed`.
4. `test_adapter_symbol_and_timeframe_mismatch_fail_closed`.
5. `test_primary_timeframe_identity_mismatch_fails_closed`.
6. `test_context_symbol_identity_mismatch_fails_closed`.
7. `test_context_dataset_identity_mismatch_fails_closed`.
8. `test_context_manifest_identity_mismatch_fails_closed`.

- [ ] **Step 1:** Write the integration tests. Run → **RED** only if the module interface is missing; otherwise they exercise Task 1 code (write before the module if running strictly task-by-task).
- [ ] **Step 2:** Run `uv run pytest tests/integration/test_ema_rsi_btc_regime_integration.py -q` → **GREEN**.
- [ ] **Step 3:** Record evidence (no commit).

---

### Task 4: E2E test (DEVELOPMENT-only)

**Files:**
- Create: `tests/e2e/test_ema_rsi_btc_regime_e2e.py`

Tests:
1. `test_regime_full_development_chain_filters_buy_only_and_preserves_holdout` — run `[0, 5000)`, assert blocked BUYs > 0, non-BUY signals preserved, holdout file bytes unchanged and `PRISTINE`, no holdout range requested.
2. `test_regime_spec_id_differs_from_baseline_and_context` — `strategy_artifact_identity` for `EmaRsiBtcRegime` differs from `baseline-v1` and from `EmaRsiBtcContext-v1`; `spec_id` differs.

- [ ] **Step 1:** Write the E2E tests. Run → **GREEN** after Task 1.
- [ ] **Step 2:** Run `uv run pytest tests/e2e/test_ema_rsi_btc_regime_e2e.py -q`.
- [ ] **Step 3:** Record evidence (no commit).

---

### Task 5: Quality gates + evidence + commit candidate

**Files:**
- Create: `docs/phases/18C/evidence/*` (logs, coverage JSON, smoke JSON).
- Create: `docs/phases/18C/commit-candidate-001.md`.

- [ ] **Step 1:** `bash harness/scripts/evidence.sh 18C tests-lab -- uv run pytest tests/lab`
- [ ] **Step 2:** `bash harness/scripts/evidence.sh 18C tests-integration -- uv run pytest tests/integration`
- [ ] **Step 3:** `bash harness/scripts/evidence.sh 18C tests-e2e -- uv run pytest tests/e2e`
- [ ] **Step 4:** `bash harness/scripts/evidence.sh 18C coverage-global -- uv run pytest --cov=src --cov-branch --cov-report=json:docs/phases/18C/evidence/coverage.json --cov-fail-under=90`
- [ ] **Step 5:** `bash harness/scripts/evidence.sh 18C coverage-18c -- uv run pytest tests/lab/test_ema_rsi_btc_regime.py --cov=lab.strategies.ema_rsi_btc_regime --cov-branch --cov-report=json:docs/phases/18C/evidence/coverage-18c.json`
- [ ] **Step 6:** `bash harness/scripts/evidence.sh 18C ruff -- uv run ruff check .`
- [ ] **Step 7:** `bash harness/scripts/evidence.sh 18C format -- uv run ruff format --check .`
- [ ] **Step 8:** `bash harness/scripts/evidence.sh 18C mypy -- uv run mypy src tests`
- [ ] **Step 9:** `bash harness/scripts/evidence.sh 18C holdout-state -- uv run python -c "import json;print(json.load(open('holdout/v1.state.json'))['state'])"`
- [ ] **Step 10:** `bash harness/scripts/evidence.sh 18C protected-runtime-diff -- git diff --exit-code HEAD -- <protected paths>`
- [ ] **Step 11:** Write `docs/phases/18C/commit-candidate-001.md` and stop at `READY_FOR_HUMAN_18C_IMPLEMENTATION_GATE`.

---

## Self-Review

- **Spec coverage:** rule, parameters, identity, causality, warmup, BUY/SELL/HOLD, tests, no-code-change constraints, and data safety each map to Task 1–5. Economic evaluation is intentionally deferred (no task).
- **Placeholders:** none; the module code is complete and the test names/assertions are explicit.
- **Type consistency:** `EmaRsiBtcRegimeConfig`, `EmaRsiBtcRegime.from_adapters`, `on_candle`, `strategy_definition`, and `decision_counts` names are used consistently across tasks.

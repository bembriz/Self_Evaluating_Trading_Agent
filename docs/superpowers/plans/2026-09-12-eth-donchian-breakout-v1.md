# EthDonchianBreakout-v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Project override:** this repository forbids `git commit`/`git push` without explicit human authorization (AGENTS.md §4.2, §7). Do not stage or commit; stop at `READY_FOR_HUMAN_PHASE_19A_IMPLEMENTATION_GATE`.

**Goal:** Implement a standalone ETH Donchian breakout strategy (`EthDonchianBreakout-v1`) gated by a new causal Wilder ADX indicator, with TDD.

**Architecture:** Add a causal `adx()` to `domain.market.indicators`; add `src/lab/strategies/eth_donchian_breakout.py` implementing the `Strategy` protocol directly (no composition with the frozen EMA/RSI strategies). Reuse `StrategyDefinition`, `ExperimentSpec`, `FrozenDatasetAdapter`, `LabSessionRunner`, `RiskEngine`, `PaperEngine`.

**Tech Stack:** Python 3.12, pytest, ruff, mypy (strict), uv.

## Global Constraints

- Frozen params: `entry_donchian_lookback=20`, `exit_donchian_lookback=10`, `adx_period=14`, `adx_min=20`.
- BUY: `close[t] > max(high[t-20:t])` AND `adx14[t] > 20`; SELL: `close[t] < min(low[t-10:t])`; strict inequalities.
- Current candle strictly excluded from both Donchian windows.
- Warmup: `t<10` HOLD; `10<=t<20` SELL only; `t>=20` ADX-unavailable blocks BUY only; SELL independent of ADX.
- ADX: first ADX at index `2n-1` (`FIRST_ADX_INDEX=27` for n=14); Wilder seed and `avg=(avg*(n-1)+value)/n`; causal.
- `RiskEngine` unchanged and authoritative; protected runtime untouched; only `domain.market.indicators` gains ADX.
- DEVELOPMENT only; `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0`, `FINAL_HOLDOUT_EXECUTIONS=0`, `HOLDOUT_STATE=PRISTINE`.
- New strategy module and new ADX code: 100% statement and branch coverage. Global coverage ≥ 90%.
- No staging, no commit, no push, no economic evaluation, no walk-forward, no holdout.

---

## File Structure

- Modify `src/domain/market/indicators.py` — add `adx`.
- Modify `tests/test_indicators.py` — ADX unit tests.
- Create `src/lab/strategies/eth_donchian_breakout.py` — strategy, config, `strategy_definition`.
- Create `tests/lab/test_eth_donchian_breakout.py` — strategy unit contract.
- Create `harness/scripts/phase19a_development_smoke.py` — DEVELOPMENT-only smoke.
- Create `tests/lab/test_phase19a_development_smoke.py` — smoke contract.
- Create `tests/integration/test_eth_donchian_breakout_integration.py`.
- Create `tests/e2e/test_eth_donchian_breakout_e2e.py`.
- Create `docs/phases/19A/evidence/` — logs and coverage.

---

### Task 1: Causal Wilder ADX

**Files:** Modify `src/domain/market/indicators.py`; Modify `tests/test_indicators.py`.

**Produces:** `adx(candles: Sequence[Candle], period: int = 14) -> list[float | None]`.

**Implementation:**

```python
def adx(candles: Sequence[Candle], period: int = 14) -> list[float | None]:
    """Average Directional Index de Wilder (causal). None durante warmup.

    TR/+DM/-DM empiezan en el índice 1. Primer suavizado en el índice period.
    Primer DX en el índice period. Primer ADX en el índice 2*period-1.
    """
    _require_positive_period(period)
    out: list[float | None] = [None] * len(candles)
    if len(candles) < 2 * period:
        return out
    trs = [0.0] * len(candles)
    plus_dm = [0.0] * len(candles)
    minus_dm = [0.0] * len(candles)
    for i in range(1, len(candles)):
        prev = candles[i - 1]
        cur = candles[i]
        trs[i] = max(
            cur.high - cur.low,
            abs(cur.high - prev.close),
            abs(cur.low - prev.close),
        )
        up = cur.high - prev.high
        down = prev.low - cur.low
        if up > down and up > 0.0:
            plus_dm[i] = up
        elif down > up and down > 0.0:
            minus_dm[i] = down

    def _seed(values: list[float]) -> float:
        return sum(values[1 : period + 1]) / period

    smooth_tr = _seed(trs)
    smooth_plus = _seed(plus_dm)
    smooth_minus = _seed(minus_dm)

    def _di(plus: float, minus: float, tr: float) -> float:
        if tr == 0.0:
            return 0.0
        return 100.0 * (plus if plus is not None else 0.0) / tr

    dx_values: list[float] = []
    for i in range(period, len(candles)):
        if i > period:
            smooth_tr = (smooth_tr * (period - 1) + trs[i]) / period
            smooth_plus = (smooth_plus * (period - 1) + plus_dm[i]) / period
            smooth_minus = (smooth_minus * (period - 1) + minus_dm[i]) / period
        plus_di = 100.0 * smooth_plus / smooth_tr if smooth_tr != 0.0 else 0.0
        minus_di = 100.0 * smooth_minus / smooth_tr if smooth_tr != 0.0 else 0.0
        denom = plus_di + minus_di
        dx_values.append(100.0 * abs(plus_di - minus_di) / denom if denom != 0.0 else 0.0)
        if len(dx_values) == period:
            avg = sum(dx_values) / period
            out[i] = avg
        elif len(dx_values) > period:
            avg = (avg * (period - 1) + dx_values[-1]) / period
            out[i] = avg
    return out
```

**ADX tests (add to `tests/test_indicators.py`):**
1. `test_adx_first_index_is_27_for_period_14` — first non-None at index 27.
2. `test_adx_values_before_first_index_are_none`.
3. `test_adx_monotonic_trend_is_strong` — steady uptrend → `adx[27] > 20`.
4. `test_adx_flat_series_is_zero` — constant candles → `adx[27] == 0.0`.
5. `test_adx_future_mutation_does_not_change_history` — corrupt candles after T, assert prefix equal.
6. `test_adx_is_deterministic`.
7. `test_adx_invalid_period_raises`.

- [ ] Step 1: Write ADX tests → run `uv run pytest tests/test_indicators.py -q` → RED.
- [ ] Step 2: Implement `adx` → run → GREEN; confirm `src/domain/market/indicators.py` 100% statements/branches.

---

### Task 2: `EthDonchianBreakout` strategy

**Files:** Create `src/lab/strategies/eth_donchian_breakout.py`; Test `tests/lab/test_eth_donchian_breakout.py`.

**Produces:** `EthDonchianBreakoutConfig`, `EthDonchianBreakout` (`strategy_name="EthDonchianBreakout"`, `version="eth-donchian-breakout-v1"`), `from_adapters`, `on_candle`, `strategy_definition`.

**Implementation:** standalone strategy precomputing `prior_high_20`, `prior_low_10` and `adx14`; `on_candle` emits BUY/SELL/HOLD with the frozen warmup rules; `from_adapters` wraps `adapter.candles`; `strategy_definition` uses sources `("lab.strategies.eth_donchian_breakout", "domain.market.indicators")` and `normalized_config` with the four frozen params.

**Strategy tests (24 mandatory):** entry BUY, equality no BUY, current-high exclusion, ADX `==20`/`<20`/unavailable no BUY, SELL, equality no SELL, current-low exclusion, SELL while ADX unavailable, SELL during `10<=t<20`, `t<10` HOLD, causal corruption, determinism, identity sensitivity (4 params), SpecId sensitivity, FINAL_HOLDOUT denied, plus constructor validation and runner-sequence fail-closed.

- [ ] Step 1: Write strategy tests → RED.
- [ ] Step 2: Implement strategy → GREEN; confirm 100% statements/branches.

---

### Task 3: DEVELOPMENT smoke + test

**Files:** Create `harness/scripts/phase19a_development_smoke.py`; Test `tests/lab/test_phase19a_development_smoke.py`.

Smoke over `[0, 5000)`: counts BUY/SELL/HOLD, asserts `FIRST_ADX_INDEX==27`, asserts all three decision paths occur, reports `FINAL_HOLDOUT_READS=0`. No PnL.

- [ ] Step 1: Write smoke test → RED. Step 2: implement → GREEN.

---

### Task 4: Integration + E2E

**Files:** Create `tests/integration/test_eth_donchian_breakout_integration.py`; Create `tests/e2e/test_eth_donchian_breakout_e2e.py`.

- Integration: real `FrozenDatasetAdapter` + unchanged `LabSessionRunner` + `PaperEngine`; events aligned; reproducibility by double run.
- E2E: DEVELOPMENT `[0, 5000)` path; strategy decisions occur; holdout file unchanged and `PRISTINE`; no holdout range requested; `SpecId` differs from baseline/context/regime.

- [ ] Step 1: Write tests. Step 2: run → GREEN.

---

### Task 5: Quality gates + evidence + commit candidate

- [ ] `bash harness/scripts/evidence.sh 19A tests-lab -- uv run pytest tests/lab`
- [ ] `bash harness/scripts/evidence.sh 19A tests-integration -- uv run pytest tests/integration`
- [ ] `bash harness/scripts/evidence.sh 19A tests-e2e -- uv run pytest tests/e2e`
- [ ] `bash harness/scripts/evidence.sh 19A coverage-global -- uv run pytest --cov=src --cov-branch --cov-report=json:docs/phases/19A/evidence/coverage.json --cov-fail-under=90`
- [ ] `bash harness/scripts/evidence.sh 19A coverage-19a -- uv run pytest tests/test_indicators.py tests/lab/test_eth_donchian_breakout.py --cov=domain.market.indicators --cov=lab.strategies.eth_donchian_breakout --cov-branch --cov-report=json:docs/phases/19A/evidence/coverage-19a.json`
- [ ] ruff / format / mypy / holdout-state / protected-runtime-diff / no-staging evidence.
- [ ] Write `docs/phases/19A/commit-candidate-001.md`; stop at `READY_FOR_HUMAN_PHASE_19A_IMPLEMENTATION_GATE`.

---

## Self-Review

- **Spec coverage:** rule, warmup table, ADX indexing, identity, tests, data safety each map to Task 1–5.
- **Placeholders:** ADX code is complete; strategy behavior is fully specified by the frozen rules.
- **Type consistency:** `adx`, `EthDonchianBreakoutConfig`, `EthDonchianBreakout`, `from_adapters`, `on_candle`, `strategy_definition` names are consistent across tasks.

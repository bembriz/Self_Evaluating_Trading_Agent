# EthBollingerMeanReversion-v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax.
>
> **Project override:** this repository forbids `git commit`/`git push` without explicit human authorization (AGENTS.md §4.2, §7). Do not stage or commit; stop at `READY_FOR_HUMAN_PHASE_20A_IMPLEMENTATION_GATE`.

**Goal:** Implement `EthBollingerMeanReversion-v1`, a standalone ETH mean-reversion strategy, plus the minimal causal `bollinger` indicator, with TDD.

**Architecture:** Add a stdlib `bollinger(values, period=20, multiplier=2.0) -> list[BollingerBands | None]` to `domain.market.indicators` (population stddev `ddof=0` via `statistics.pstdev`). Add `src/lab/strategies/eth_bollinger_mean_reversion.py` implementing the `Strategy` protocol directly. Reuse `adx`, `StrategyDefinition`, `ExperimentSpec`, `FrozenDatasetAdapter`, `LabSessionRunner`, `RiskEngine`, `PaperEngine`.

**Tech Stack:** Python 3.12, pytest, ruff, mypy (strict), uv.

## Global Constraints

- `bollinger_period=20`, `bollinger_stddev_multiplier=2.0`, `adx_period=14`, `adx_max=20.0`.
- Bollinger includes the current confirmed close; `ddof=0`; first index 19; causal.
- Decision order: (1) `close[t] >= MIDDLE[t]` → SELL; (2) else re-entry BUY `close[t-1] < LOWER[t-1]` (strict) AND `close[t] >= LOWER[t]` (inclusive) AND `ADX[t] < 20.0` (strict); (3) HOLD.
- SELL precedence over BUY; SELL independent of ADX; no global ADX warmup.
- No RSI, no BTC, no LLM, no new framework; no protected-runtime change.
- DEVELOPMENT only. `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0`, `FINAL_HOLDOUT_EXECUTIONS=0`, `HOLDOUT_STATE=PRISTINE`.
- New strategy and new Bollinger code: 100% statement and branch coverage. Global coverage ≥ 90%.

---

## Task 1: Causal Bollinger indicator

**Files:** Modify `src/domain/market/indicators.py`; Modify `tests/test_indicators.py`.

**Produces:** `BollingerBands` (frozen dataclass: `middle`, `upper`, `lower`) and `bollinger(values, period=20, multiplier=2.0) -> list[BollingerBands | None]`.

```python
@dataclass(frozen=True, slots=True)
class BollingerBands:
    middle: float
    upper: float
    lower: float


def bollinger(
    values: Sequence[float], period: int = 20, multiplier: float = 2.0
) -> list[BollingerBands | None]:
    """Bandas de Bollinger causales (desviación poblacional, ddof=0)."""
    _require_positive_period(period)
    if not math.isfinite(multiplier) or multiplier <= 0.0:
        raise ValueError(f"multiplier must be finite and > 0: {multiplier!r}")
    out: list[BollingerBands | None] = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        middle = sum(window) / period
        std = statistics.pstdev(window)
        out[i] = BollingerBands(
            middle=middle,
            upper=middle + multiplier * std,
            lower=middle - multiplier * std,
        )
    return out
```

Add `import math` and `import statistics` at the top.

**Tests (add to `tests/test_indicators.py`):** first ready index 19; indices 0..18 None; population stddev `ddof=0` on a hand fixture (`[1,2,3,4]`, period 4, multiplier 2.0 → middle 2.5, std `sqrt(1.25)`, upper `2.5+2*sqrt(1.25)`); exact middle/upper/lower; flat values → std 0 and upper=middle=lower; causal prefix equality; future mutation cannot change earlier bands; deterministic; invalid period raises; invalid multiplier (0, -1, inf, nan) raises.

- [ ] Step 1: write tests → RED. Step 2: implement → GREEN; `domain.market.indicators` 100%.

---

## Task 2: `EthBollingerMeanReversion` strategy

**Files:** Create `src/lab/strategies/eth_bollinger_mean_reversion.py`; Test `tests/lab/test_eth_bollinger_mean_reversion.py`.

**Produces:** `EthBollingerMeanReversionConfig(bollinger_period=20, bollinger_stddev_multiplier=2.0, adx_period=14, adx_max=20.0)`, `EthBollingerMeanReversion` (`strategy_name="EthBollingerMeanReversion"`, `version="eth-bollinger-mean-reversion-v1"`), `from_adapters`, `on_candle`, `strategy_definition`.

**Implementation:** precompute `bollinger(closes, period, multiplier)` and `adx(candles, adx_period)`; `on_candle` applies the frozen order (SELL → BUY → HOLD); validates config (period/multiplier via `bollinger`; `adx_period > 0`; `adx_max` finite `>= 0`); empty candles → `ValueError`; runner sequence mismatch/exhausted → `ValueError`.

**Tests (24):** BUY on excursion+re-entry+ADX<20; previous close equal/greater than lower → no BUY; current close below lower → no BUY; current close equal lower satisfies re-entry; ADX `<20` permits, `==20` blocks, `>20` blocks, unavailable blocks; `close >= middle` → SELL; `close == middle` → SELL; SELL independent of ADX (None/`<20`/`==20`/`>20`); simultaneous BUY+SELL conditions → SELL; Bollinger warmup HOLD; BUY blocked before inputs ready; future corruption; determinism; sequence mismatch; identity sensitivity (4 params); SpecId sensitivity; FINAL_HOLDOUT denied.

Fixtures (frozen defaults): BUY series `[10.0]*32` with index 30 = `9.9`, index 31 = `9.97`; ADX-unavailable series `[10.0]*26` with 24 = `9.9`, 25 = `9.97`; SELL series index 31 = `10.0`; SELL@19 flat `[10.0]*20`. Candles: `high=close+0.05`, `low=close-0.05`, `open=close`.

- [ ] Step 1: write tests → RED. Step 2: implement → GREEN; 100% statements/branches.

---

## Task 3: DEVELOPMENT smoke

**Files:** Create `harness/scripts/phase20a_development_smoke.py`; Test `tests/lab/test_phase20a_development_smoke.py`.

Smoke over `[0, 5000)`: counts BUY/SELL/HOLD, asserts Bollinger ready index 19 and ADX ready index 27, asserts all three decision paths occur and no holdout read. No PnL.

- [ ] Step 1: write test → RED. Step 2: implement → GREEN.

---

## Task 4: Integration + E2E

**Files:** Create `tests/integration/test_eth_bollinger_mean_reversion_integration.py`; Create `tests/e2e/test_eth_bollinger_mean_reversion_e2e.py`.

- Integration: real `FrozenDatasetAdapter` + unchanged `LabSessionRunner` + `PaperEngine`; events aligned; reproducibility by double run.
- E2E: DEVELOPMENT `[0, 5000)`; strategy decisions occur; holdout file unchanged and `PRISTINE`; `SpecId` differs from baseline/context/regime/donchian.

- [ ] Step 1: write tests. Step 2: run → GREEN.

---

## Task 5: Quality gates + evidence + commit candidate

- [ ] `bash harness/scripts/evidence.sh 20A tests-lab -- uv run pytest tests/lab`
- [ ] `bash harness/scripts/evidence.sh 20A tests-integration -- uv run pytest tests/integration`
- [ ] `bash harness/scripts/evidence.sh 20A tests-e2e -- uv run pytest tests/e2e`
- [ ] `bash harness/scripts/evidence.sh 20A coverage-global -- uv run pytest --cov=src --cov-branch --cov-report=json:docs/phases/20A/evidence/coverage.json --cov-fail-under=90`
- [ ] `bash harness/scripts/evidence.sh 20A coverage-20a -- uv run pytest tests/test_indicators.py tests/lab/test_eth_bollinger_mean_reversion.py --cov=lab.strategies.eth_bollinger_mean_reversion --cov-branch --cov-report=json:docs/phases/20A/evidence/coverage-20a.json`
- [ ] ruff / format / mypy / holdout-state / protected-runtime-diff / no-staging evidence.
- [ ] Write `docs/phases/20A/commit-candidate-001.md`; stop at `READY_FOR_HUMAN_PHASE_20A_IMPLEMENTATION_GATE`.

---

## Self-Review

- **Spec coverage:** Bollinger contract, decision order/precedence, boundaries, warmup, identity, tests, safety each map to Tasks 1–5.
- **Placeholders:** Bollinger code is complete; strategy behavior is fully specified by the frozen rules.
- **Type consistency:** `BollingerBands`, `bollinger`, `EthBollingerMeanReversionConfig`, `EthBollingerMeanReversion`, `from_adapters`, `on_candle`, `strategy_definition` are consistent across tasks.

# EmaRsiBtcContext-v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a DEVELOPMENT-only Strategy Lab candidate that preserves `EmaRsiBaseline` and filters only its ETH BUY candidates with causal `BTC EMA20 > EMA50` context.

**Architecture:** A single lab strategy module composes `EmaRsiBaseline`, validates preloaded ETH/BTC candles 1:1, precomputes causal BTC EMA context with the existing indicator, and validates the runner's ETH sequence on every call. Existing Phase 17B identity and open-ended `ExperimentSpec` mappings are reused without changing either subsystem or `LabSessionRunner`.

**Tech Stack:** Python 3.12, dataclasses, existing domain EMA/baseline, pytest, pytest-cov, ruff, mypy, Strategy Lab runtime-parity components.

## Global Constraints

- HEAD base is `f6899b5`; preserve unrelated dirty worktree changes.
- Do not modify `LabSessionRunner`, `PaperEngine`, `RiskEngine`, portfolio, `EmaRsiBaseline`, `strategy.py`, or any protected runtime path.
- Do not stage, commit, push, run walk-forward, or access FINAL_HOLDOUT.
- Use only DEVELOPMENT `[0, 62208)` real data.
- BTC filters BUY only; baseline SELL and HOLD objects pass through unchanged even during BTC warmup.
- BTC context at T uses only BTC candles with timestamp `<= T`; no filling or timestamp substitution.
- Smoke counters are strategy decisions, not fills or orders, and make no performance claim.
- New Phase 18A production code requires 100% statement and branch coverage; global coverage remains at least 90%.

---

### Task 1: Candidate Decision Contract And Alignment

**Files:**
- Create: `tests/lab/test_ema_rsi_btc_context.py`
- Create: `src/lab/strategies/__init__.py`
- Create: `src/lab/strategies/ema_rsi_btc_context.py`

**Interfaces:**
- Consumes: `Candle`, `ema`, `Action`, `Signal`, `EmaRsiBaseline`, `EmaRsiConfig`, and `FrozenDatasetAdapter`.
- Produces: `EmaRsiBtcContextConfig`, `EmaRsiBtcContext`, `EmaRsiBtcContext.from_adapters`, and `strategy_definition`.

- [ ] **Step 1: Write focused failing unit tests**

Create deterministic candle helpers and tests that exercise:

```python
strategy = EmaRsiBtcContext(
    primary_candles=eth,
    btc_candles=btc,
    config=EmaRsiBtcContextConfig(
        ema_fast=2,
        ema_slow=3,
        rsi_period=2,
        rsi_exit=80.0,
        btc_ema_fast=2,
        btc_ema_slow=3,
    ),
)
signals = tuple(strategy.on_candle(candle) for candle in eth)
```

Assert the 14 required behaviors: confirmed BUY; blocked BUY; SELL under bullish and bearish BTC; HOLD pass-through; BUY blocked during BTC warmup; aligned timestamps accepted; length/timestamp mismatch rejected; future BTC mutation does not alter outputs through T; repeat construction is deterministic; BTC config changes artifact identity; nested context dataset changes SpecId; baseline defaults/source remain unchanged; holdout ranges remain denied without opening official holdout data. Also cover empty input, invalid periods, wrong adapter symbols/dataset/timeframe/ranges, divergent runner candles, and extra calls.

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
uv run pytest tests/lab/test_ema_rsi_btc_context.py -q
```

Expected: collection fails because `lab.strategies.ema_rsi_btc_context` does not exist.

- [ ] **Step 3: Implement the minimal candidate**

Use these exact public signatures:

```python
@dataclass(frozen=True, slots=True)
class EmaRsiBtcContextConfig:
    ema_fast: int = 20
    ema_slow: int = 50
    rsi_period: int = 14
    rsi_exit: float = 80.0
    btc_ema_fast: int = 20
    btc_ema_slow: int = 50


class EmaRsiBtcContext:
    strategy_name = "EmaRsiBtcContext"
    version = "ema-rsi-btc-context-v1"
```

- `EmaRsiBtcContext.__init__(self, *, primary_candles: Sequence[Candle], btc_candles: Sequence[Candle], config: EmaRsiBtcContextConfig | None = None) -> None`
- `EmaRsiBtcContext.from_adapters(cls, *, primary: FrozenDatasetAdapter, context: FrozenDatasetAdapter, config: EmaRsiBtcContextConfig | None = None) -> EmaRsiBtcContext`
- `EmaRsiBtcContext.on_candle(self, candle: Candle) -> Signal`
- `strategy_definition(config: EmaRsiBtcContextConfig | None = None) -> StrategyDefinition`

The constructor copies inputs to tuples, validates non-empty equal lengths and timestamp equality, calculates `ema(closes, btc_ema_fast)` and `ema(closes, btc_ema_slow)`, and stores `None` until both values exist. `on_candle` validates the exact next preloaded ETH candle, delegates once to baseline, increments position, returns SELL/HOLD unchanged, confirms BUY only for context `True`, and otherwise returns HOLD/`btc_context_block` preserving intensity.

`from_adapters` requires primary `ETHUSDT`, context `BTCUSDT`, both `15m`, same dataset id, row bounds, manifest SHA, and candle timestamps. `strategy_definition` uses only Phase 17B `StrategyDefinition` with sources `lab.strategies.ema_rsi_btc_context`, `domain.trading.strategy`, and `domain.market.indicators` and normalized ETH/BTC config.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
uv run pytest tests/lab/test_ema_rsi_btc_context.py -q
```

Expected: all candidate unit tests pass.

- [ ] **Step 5: Refactor only duplication in test helpers and rerun**

Keep all strategy behavior in the one candidate module. Do not extract context frameworks or modify existing modules.

### Task 2: Runtime-Parity Integration And E2E

**Files:**
- Create: `tests/integration/test_ema_rsi_btc_context_integration.py`
- Create: `tests/e2e/test_ema_rsi_btc_context_e2e.py`

**Interfaces:**
- Consumes: Task 1 candidate, `FrozenDatasetAdapter.from_repo`, unchanged `LabSessionRunner`, `PaperEngine`, `ExperimentSpec`, Phase 17B identity.
- Produces: DEVELOPMENT-only integration and complete candidate-chain proof.

- [ ] **Step 1: Write failing integration and E2E tests**

Integration opens ETH/BTC adapters for the same small DEVELOPMENT range, builds the candidate with `from_adapters`, runs unchanged `LabSessionRunner`, and proves event timestamps match the primary adapter and repeated runs have identical traces/metrics.

E2E builds nested dataset input exactly as:

```python
dataset={
    "primary": {
        "dataset_id": "BYBIT_ETHBTC_V001",
        "symbol": "ETHUSDT",
        "timeframe": "15m",
        "row_start": 0,
        "row_end": end,
    },
    "context": {
        "dataset_id": "BYBIT_ETHBTC_V001",
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "row_start": 0,
        "row_end": end,
    },
}
```

It computes the existing artifact identity, registers/spec-links the run as needed, executes the unchanged runner on DEVELOPMENT only, asserts at least one blocked BUY in the selected functional range, and verifies holdout state bytes remain unchanged. Count strategy decisions from fresh direct strategy instances, not engine fills.

- [ ] **Step 2: Run tests and confirm any failure is the missing integration behavior**

Run:

```bash
uv run pytest tests/integration/test_ema_rsi_btc_context_integration.py tests/e2e/test_ema_rsi_btc_context_e2e.py -q
```

- [ ] **Step 3: Make minimal test/setup corrections without runtime edits**

Only adjust candidate/test composition. If protected runtime modification appears necessary, stop with `NEEDS_POST_CERTIFICATION_CHANGE` rather than working around it.

- [ ] **Step 4: Rerun integration and E2E to GREEN**

Expected: both suites pass using only `[0, end)` where `end <= 62208`.

### Task 3: Reproducible Development Smoke

**Files:**
- Create: `harness/scripts/phase18a_development_smoke.py`
- Create: `docs/phases/18A/evidence/development-smoke.json`
- Create: `docs/phases/18A/evidence/strategy-definition.md`
- Create: `docs/phases/18A/evidence/alignment.md`

**Interfaces:**
- Consumes: official ETH/BTC adapters, baseline, candidate, DEVELOPMENT split constants.
- Produces: deterministic JSON strategy-decision counters and non-performance evidence.

- [ ] **Step 1: Add a smoke test before the script implementation**

Add a test that invokes the script's pure counting function twice over injected candles and proves stable counts where:

```python
baseline_buy_signals >= btc_context_buy_signals
btc_blocked_buys == baseline_buy_signals - btc_context_buy_signals
btc_blocked_buys > 0
```

- [ ] **Step 2: Verify RED, then implement the smallest smoke script**

Use a fixed range wholly within DEVELOPMENT, starting with `[0, 5000)`. The script loads exactly matching ETH/BTC adapters, counts direct strategy output actions from fresh instances, rejects zero blocked buys, and prints canonical JSON. It must not calculate or compare PnL.

- [ ] **Step 3: Run the smoke through evidence capture**

Run the script via `harness/scripts/evidence.sh`, then preserve the JSON output as `development-smoke.json`. If `[0, 5000)` has no blocked BUY, choose the next fixed DEVELOPMENT range based only on signal availability and document that reason.

- [ ] **Step 4: Write definition and alignment evidence**

Document exact strategy rules, source identity inputs, dataset hashes, row bounds, timestamp count/equality, causal EMA semantics, and `FINAL_HOLDOUT_READS=0` / `FINAL_HOLDOUT_EXECUTIONS=0`.

### Task 4: Full Verification And Gate Package

**Files:**
- Create: `docs/phases/18A/evidence/*.log`
- Create: `docs/phases/18A/evidence/coverage.json`
- Create: `docs/phases/18A/evidence/coverage-18a.json`
- Create: `docs/phases/18A/commit-candidate-001.md`

**Interfaces:**
- Consumes: all implementation/tests/evidence from Tasks 1-3.
- Produces: auditable Phase 18A human-gate package, with no Git state mutation.

- [ ] **Step 1: Capture required test evidence separately**

Run each command with `bash harness/scripts/evidence.sh 18A <name> -- <command>`:

```bash
uv run pytest tests/lab
uv run pytest tests/integration
uv run pytest tests/e2e
uv run pytest --cov=src --cov-branch --cov-report=json:docs/phases/18A/evidence/coverage.json --cov-fail-under=90
uv run pytest tests/lab/test_ema_rsi_btc_context.py tests/integration/test_ema_rsi_btc_context_integration.py tests/e2e/test_ema_rsi_btc_context_e2e.py --cov=lab.strategies.ema_rsi_btc_context --cov-branch --cov-report=json:docs/phases/18A/evidence/coverage-18a.json --cov-fail-under=100
```

- [ ] **Step 2: Capture quality evidence separately**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
```

- [ ] **Step 3: Verify protected runtime and holdout state**

Use read-only Git diff commands to prove all protected paths are clean relative to HEAD. Verify the existing holdout state remains `PRISTINE`; do not open any official holdout range.

- [ ] **Step 4: Refresh graph and calculate blast radius**

Re-index the changed worktree, run `detect_changes`, and call `check_index_coverage` for every changed/cited path. Record exact impacted modules/callers and limitations.

- [ ] **Step 5: Prepare the unstaged commit candidate**

Populate every applicable section of `docs/phases/18A/commit-candidate-001.md`, explicitly marking staging, commit, post-commit reindex, push, walk-forward, edge, and promotion as not performed/not evaluated.

- [ ] **Step 6: Final verification and stop**

Inspect `git status`, `git diff --check`, evidence exit codes, coverage JSON totals, smoke counters, protected diff, and holdout state. Print the exact Phase 18A completion block ending in `READY_FOR_HUMAN_18A_GATE` and stop without staging.

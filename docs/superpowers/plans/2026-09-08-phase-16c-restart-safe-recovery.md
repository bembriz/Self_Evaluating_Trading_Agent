# Phase 16c.1 — Restart-safe Recovery — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `PaperRunner` restart-safe so `NO_RESTART_TRACE == RESTART_TRACE` with idempotent, atomic persistence and a REST→WS handoff with no loss window.

**Architecture:** Recovery = deterministic event replay (Option B). Persisted `market_candles` + `paper_trade_events` are replayed through the same pure pipeline (`_process`) to rebuild all in-memory state; recomputed events are verified against persisted events (STOP on divergence). Only non-derivable state (kill switch) is persisted explicitly. Each live candle is persisted atomically (candle + event) in one PostgreSQL transaction.

**Tech Stack:** Python 3.12, SQLAlchemy 2 (async, psycopg3), Alembic, pytest/pytest-asyncio, uv.

## Global Constraints

- Base commit: `9fecca6` (branch `fix/phase-16c-restart-safe`).
- `strategy_version = baseline-v1`, `risk_config_version = risk-v1` — NO changes.
- fees/slippage/risk params — NO changes.
- No LLM/RAG/new trading features/microservices.
- Persisted fills are authoritative; replay only verifies (`recomputed == persisted`), never silently replaces a fill.
- Divergence ⇒ STOP RECOVERY, log ERROR, no trading.
- Idempotency key for events: `(session_id, symbol, timeframe, timestamp_ms)`.
- Backfill only CONFIRMED candles (`candle_close_time <= recovery_cutoff`); never partial candles.
- Migrations written but NOT applied to production (local test only until USER GATE).

---

### Task 1: Runtime 45/0 + preflight

**Files:**
- Modify: `src/settings.py` (default `paper_max_runtime_days`)
- Modify: `src/interfaces/cli/paper_runner.py` (deadline + preflight)
- Test: `tests/test_cli_paper_runner.py`, `tests/test_settings.py`

**Interfaces:**
- Consumes: existing `Settings`, `run_paper_runner`.
- Produces: `paper_max_runtime_days: int = 45`; `MIN_RUNTIME_FOR_CERTIFICATION_DAYS = 45`; `resolve_deadline(seconds: int | None, max_days: int) -> float | None`; `preflight_runtime(max_days: int, session_id: str | None) -> None` (raises on violation).

- [ ] **Step 1: failing tests** — `test_paper_runner_settings_defaults` expects `paper_max_runtime_days == 45`; `test_max_runtime_days_zero_means_unlimited`; `test_preflight_rejects_short_runtime` (session set, days=7 → raise); `test_preflight_allows_45`; `test_preflight_allows_unlimited`.
- [ ] **Step 2: run → FAIL**
- [ ] **Step 3: implement** — settings default 45; `resolve_deadline` returns `None` when `0`; `preflight_runtime` raises `ValueError` when session set and `0 < max_days < 45`.
- [ ] **Step 4: run → PASS**
- [ ] **Step 5: commit**

---

### Task 2: Kill switch persistence (MUST_HAVE)

**Files:**
- Modify: `src/interfaces/cli/paper_runner.py` (load + attach)
- Modify: `src/application/services/paper_runner.py` (accept kill switch state)
- Test: `tests/test_paper_runner.py`

**Interfaces:**
- Consumes: `SqlAlchemySystemStateRepository.get/set`, `KillSwitch(initial_state=...)`, `PaperEngine.attach_kill_switch`.
- Produces: `KillSwitchState` JSON shape `{active, reason, activated_at_ms}` under key `kill_switch`.

- [ ] **Step 1: failing tests** — `test_paper_runner_restores_kill_switch_from_state` (a `KillSwitchState(active=True, reason="x")` serialized into system_state is reloaded and attached so `engine.kill_switch_state.active is True`).
- [ ] **Step 2: run → FAIL**
- [ ] **Step 3: implement** — `PaperRunner` accepts optional `kill_switch` param; CLI loads from `system_state` key `kill_switch` and attaches.
- [ ] **Step 4: run → PASS**
- [ ] **Step 5: commit**

---

### Task 3: market_candles migration 0009 + model (partial unique)

**Files:**
- Create: `migrations/versions/0009_market_candles_paper_source.py`
- Modify: `src/infrastructure/database/models.py` (`MarketCandle` + `Index` with `postgresql_where`)
- Test: `tests/integration/test_alembic.py` (extended), `tests/integration/test_market_repository.py`

**Interfaces:**
- Produces columns: `session_id`, `confirmed`, `source` (default `'download'`), `created_at`.
- Produces indexes: `uq_market_candles_download` (partial, `WHERE source='download'`), `uq_market_candles_paper` (partial, `WHERE source='paper-live'`), `ck_market_candles_paper_session`, `ix_market_candles_session_ts`.

- [ ] **Step 1: failing tests** — migration up/down round-trips; two `paper-live` sessions can insert same `(symbol, tf, ts)`; `download` row with `session_id NULL` is valid; `paper-live` row with NULL session_id is rejected by CHECK.
- [ ] **Step 2: run → FAIL**
- [ ] **Step 3: implement** — model columns + `Index(..., postgresql_where=text("source = 'download'"), unique=True)`; `CheckConstraint`; migration mirrors it.
- [ ] **Step 4: run → PASS**
- [ ] **Step 5: commit**

---

### Task 4: paper_trade_events idempotency key (migration 0010)

**Files:**
- Create: `migrations/versions/0010_paper_trade_events_idempotency.py`
- Modify: `src/infrastructure/database/models.py` (`PaperTradeEventRecord` unique constraint)
- Modify: `src/infrastructure/database/repositories.py` (`add` → upsert)
- Test: `tests/integration/test_paper_trading_repository.py`

**Interfaces:**
- Produces: `uq_paper_trade_events_session_symbol_tf_ts UNIQUE (session_id, symbol, timeframe, timestamp_ms)`; `add` uses `pg_insert(...).on_conflict_do_nothing`.

- [ ] **Step 1: failing tests** — duplicate `(session_id, symbol, tf, ts)` insert is a no-op (no row count increase).
- [ ] **Step 2: run → FAIL**
- [ ] **Step 3: implement** — constraint + upsert.
- [ ] **Step 4: run → PASS**
- [ ] **Step 5: commit**

---

### Task 5: Candle repository source-aware (paper-live) + session range

**Files:**
- Modify: `src/application/ports/market_repositories.py` (add paper-live methods)
- Modify: `src/infrastructure/database/repositories.py`
- Test: `tests/integration/test_market_repository.py`

**Interfaces:**
- Produces: `upsert_paper(session_id, symbol, timeframe, candles) -> int` (ON CONFLICT on partial index `WHERE source='paper-live'`); `session_range(session_id, symbol, timeframe, start_ms, end_ms) -> list[Candle]`; `last_persisted_ms(session_id, symbol, timeframe) -> int | None`.

- [ ] **Step 1: failing tests** — upsert_paper dedup; session_range returns only that session; last_persisted_ms.
- [ ] **Step 2: run → FAIL**
- [ ] **Step 3: implement**
- [ ] **Step 4: run → PASS**
- [ ] **Step 5: commit**

---

### Task 6: Atomic per-candle unit (candle + event) in `_run_loop`

**Files:**
- Modify: `src/application/services/paper_runner.py` (`PaperRunner` accepts `candle_repo`; `handle_kline` upserts candle + event)
- Modify: `src/interfaces/cli/paper_runner.py` (wire candle_repo; commit-failure recovery)
- Test: `tests/test_paper_runner.py`, `tests/test_cli_paper_runner.py`

**Interfaces:**
- Consumes: `MarketCandleRepository.upsert_paper`.
- Produces: `handle_kline` persists candle + event in the same session; on `commit()` failure, `_run_loop` raises/rolls back and does NOT continue with advanced RAM.

- [ ] **Step 1: failing tests** — `test_handle_kline_persists_candle_and_event` (fake repos record both); `test_commit_failure_stops_processing` (fake commit raises → loop halts, no further candles processed).
- [ ] **Step 2: run → FAIL**
- [ ] **Step 3: implement** — `PaperRunner` gets `candle_repo`; `handle_kline` upserts candle then event; `_run_loop` wraps commit; on exception, stop.
- [ ] **Step 4: run → PASS**
- [ ] **Step 5: commit**

---

### Task 7: Deterministic recovery replay + divergence detection

**Files:**
- Create: `src/application/services/recovery.py` (or extend `paper_runner.py`)
- Modify: `src/application/services/paper_runner.py` (`_process` pure method)
- Test: `tests/test_recovery.py`

**Interfaces:**
- Consumes: `PaperRunner._process(symbol, timeframe, candle) -> PaperTradeEvent | None` (pure, no persistence).
- Produces: `PaperRunner.replay(candles: list[tuple[str,str,Candle]], persisted: Mapping[(str,str,int), PaperTradeEvent]) -> None` raising `RecoveryDivergenceError` / `RecoveryGapError`; `events_equivalent(a, b, tol=1e-9) -> bool`.

- [ ] **Step 1: failing tests** — replay reproduces portfolio/position/equity; replay of identical candles yields `events_equivalent == True`; a mutated persisted event raises `RecoveryDivergenceError`; missing persisted event raises `RecoveryGapError`.
- [ ] **Step 2: run → FAIL**
- [ ] **Step 3: implement**
- [ ] **Step 4: run → PASS**
- [ ] **Step 5: commit**

---

### Task 8: Gap backfill + REST→WS handoff (no loss window)

**Files:**
- Modify: `src/interfaces/cli/paper_runner.py` (handoff sequence)
- Create: `src/application/services/backfill.py`
- Test: `tests/test_backfill.py`

**Interfaces:**
- Consumes: `MarketDataClient.fetch_candles`.
- Produces: `handoff(recover, backfill, subscribe)`: restore DB → REST backfill to cutoff T0 → subscribe WS → second gap check to T1 → dedup → continue; only `candle_close_time <= cutoff` processed.

- [ ] **Step 1: failing tests** — (a) candle closes between backfill and subscribe → processed exactly once; (b) REST returns last closed + current open candle → only closed processed; (c) 1 lost candle / N lost candles recovered in order; (d) no gap → no-op.
- [ ] **Step 2: run → FAIL**
- [ ] **Step 3: implement**
- [ ] **Step 4: run → PASS**
- [ ] **Step 5: commit**

---

### Task 9: Integrated restart-parity E2E

**Files:**
- Create: `tests/e2e/test_e2e_restart_parity.py`
- Test: `tests/integration/test_recovery_roundtrip.py`

**Interfaces:**
- Produces: E2E-1 restart mid-position (residual=0), E2E-2 restart daily-loss, E2E-6..9 (gap/overlap), E2E-10 crash-before/after-commit, commit-failure recovery, kill-switch survives restart.

- [ ] **Step 1: write E2E** (replay with fake repos + real engine; Postgres-backed integration for the roundtrip).
- [ ] **Step 2: run → FAIL (or env-blocked: Postgres required)**
- [ ] **Step 3: implement remaining glue**
- [ ] **Step 4: run → PASS (unit; integration blocked on local Postgres)**
- [ ] **Step 5: commit**

# Phase 16 Paper Trading Certification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic Paper Trading Certification framework that tracks real evidence and keeps the phase gate pending until PRD thresholds are actually met.

**Architecture:** Use a small harness CLI to validate a versioned certification state file and generate auditable reports. Do not couple certification to order execution; it reads evidence and reports status.

**Tech Stack:** Python 3.12, stdlib JSON/dataclasses/pathlib, existing harness scripts, pytest, ruff, codebase-memory-mcp.

## Global Constraints

- No artificial trades to satisfy certification.
- No LIVE enablement in Phase 16.
- No dependency installation without approved Dependency Proposal.
- No direct edits to `harness/state/progress.yaml`; use `harness/scripts/progress.py`.
- No commit without explicit user authorization.
- Every gate-relevant command must be captured via `harness/scripts/evidence.sh`.

---

### Task 1: Scaffold Phase 16

**Files:**
- Create: `docs/phases/16/evidence/`
- Create: `docs/phases/phase-16-report.md`
- Create: `docs/uat/phase-16-uat.md`
- Modify via script only: `harness/state/progress.yaml`

**Interfaces:**
- Consumes: `harness/scripts/new_phase.py --phase 16`
- Produces: phase docs and `estado: in_progress`

- [ ] **Step 1: Run scaffold with evidence**

Run: `bash harness/scripts/evidence.sh 16 scaffold -- python3 harness/scripts/new_phase.py --phase 16`

Expected: exit 0; phase 16 dirs/report/UAT exist; ledger phase status is `in_progress`.

- [ ] **Step 2: Verify scaffold**

Run: `python3 harness/scripts/progress.py report`

Expected: Phase 16 shows `in_progress`; no Phase 17 work starts.

---

### Task 2: Certification Domain Logic

**Files:**
- Create: `harness/scripts/paper_certification.py`
- Create: `harness/tests/test_paper_certification.py`

**Interfaces:**
- Produces: `evaluate_state(state: dict[str, object]) -> CertificationResult`
- Produces: `CertificationResult.status: str` with values `PASS`, `PENDING`, `INVALIDATED`
- Produces: `CertificationResult.reasons: list[str]`

- [ ] **Step 1: Write failing tests for thresholds**

Add tests that assert:

```python
def test_certification_passes_only_with_all_thresholds() -> None:
    state = {
        "strategy_version": "baseline-v1",
        "strategy_hash": "abc",
        "active_strategy_hash": "abc",
        "calendar_days": 30,
        "trade_count": 200,
        "market_regimes": ["trend", "range"],
        "periodic_reports": ["docs/phases/16/evidence/report-day-01.md"],
    }

    result = evaluate_state(state)

    assert result.status == "PASS"
    assert result.reasons == []
```

Also test each missing threshold returns `PENDING` with the specific reason.

- [ ] **Step 2: Run tests red**

Run: `uv run pytest harness/tests/test_paper_certification.py -q`

Expected: FAIL because `paper_certification.py` does not exist yet.

- [ ] **Step 3: Implement minimal logic**

Create `CertificationResult` dataclass and `evaluate_state` with exact threshold checks:

```python
MIN_DAYS = 30
MIN_TRADES = 200
MIN_REGIMES = 2
```

Return `INVALIDATED` when `strategy_hash != active_strategy_hash`.

- [ ] **Step 4: Run tests green**

Run: `uv run pytest harness/tests/test_paper_certification.py -q`

Expected: PASS.

---

### Task 3: Certification CLI and State File

**Files:**
- Modify: `harness/scripts/paper_certification.py`
- Create: `docs/phases/16/certification-state.json`
- Modify: `harness/tests/test_paper_certification.py`

**Interfaces:**
- Consumes: `--state docs/phases/16/certification-state.json`
- Consumes: `--report docs/phases/16/PAPER_CERTIFICATION_REPORT.md`
- Produces: printed status and a Markdown report

- [ ] **Step 1: Write failing CLI test**

Add a test that writes a pending state file, calls `main([...])`, and asserts:

```python
assert code == 0
assert "PENDING" in report.read_text(encoding="utf-8")
assert "calendar_days 0/30" in report.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run CLI test red**

Run: `uv run pytest harness/tests/test_paper_certification.py -q`

Expected: FAIL because `main`/report writing is missing.

- [ ] **Step 3: Implement CLI**

Add argparse options `--state` and `--report`. Load JSON, evaluate it, write a report with status and reasons. Return exit 0 for `PASS`, `PENDING`, and `INVALIDATED`; corrupt JSON returns exit 2.

- [ ] **Step 4: Add initial state**

Create `docs/phases/16/certification-state.json` with:

```json
{
  "strategy_version": "baseline-v1",
  "strategy_hash": "pending-live-paper-hash",
  "active_strategy_hash": "pending-live-paper-hash",
  "calendar_days": 0,
  "trade_count": 0,
  "market_regimes": [],
  "periodic_reports": []
}
```

- [ ] **Step 5: Run CLI with evidence**

Run: `bash harness/scripts/evidence.sh 16 certification-initial -- python3 harness/scripts/paper_certification.py --state docs/phases/16/certification-state.json --report docs/phases/16/PAPER_CERTIFICATION_REPORT.md`

Expected: exit 0; report says `PENDING` with 0/30 days, 0/200 trades, 0/2 regimes.

---

### Task 4: Inmutability Check

**Files:**
- Modify: `harness/scripts/paper_certification.py`
- Modify: `harness/tests/test_paper_certification.py`
- Create: `docs/phases/16/evidence/strategy-hash.log`

**Interfaces:**
- Consumes: strategy/risk relevant files hash from command evidence
- Produces: invalidation when stored hash differs from active hash

- [ ] **Step 1: Write failing invalidation test**

Add test:

```python
def test_strategy_hash_change_invalidates_certification() -> None:
    result = evaluate_state({
        "strategy_version": "baseline-v1",
        "strategy_hash": "old",
        "active_strategy_hash": "new",
        "calendar_days": 30,
        "trade_count": 200,
        "market_regimes": ["trend", "range"],
        "periodic_reports": ["x.md"],
    })

    assert result.status == "INVALIDATED"
    assert "strategy hash changed" in result.reasons
```

- [ ] **Step 2: Run test red if missing**

Run: `uv run pytest harness/tests/test_paper_certification.py::test_strategy_hash_change_invalidates_certification -q`

Expected: FAIL until invalidation is implemented.

- [ ] **Step 3: Implement invalidation reason**

Ensure `evaluate_state` checks hash mismatch before threshold checks and returns only invalidation reasons.

- [ ] **Step 4: Record current strategy hash evidence**

Run: `bash harness/scripts/evidence.sh 16 strategy-hash -- bash -c 'sha256sum src/domain/trading/strategy.py src/domain/risk/*.py config/paper.yaml'`

Expected: exit 0; no secrets included.

---

### Task 5: Reports, UAT, and Gate State

**Files:**
- Modify: `docs/phases/phase-16-report.md`
- Modify: `docs/uat/phase-16-uat.md`
- Modify via script only: `harness/state/progress.yaml`

**Interfaces:**
- Consumes: evidence logs from Tasks 1-4
- Produces: Phase 16 in progress with framework deliverables done and real-certification thresholds pending

- [ ] **Step 1: Mark framework/report deliverables only when evidence exists**

Use `progress.py mark-done` for deliverables that are actually complete. Do not mark `certificacion-30-dias`, `certificacion-200-trades`, or `certificacion-2-regimenes` until real evidence exists.

- [ ] **Step 2: Block or leave pending real thresholds**

If paper trading has not accumulated real evidence, run:

`python3 harness/scripts/progress.py block --phase 16 --deliverable certificacion-30-dias --motivo "requiere 30 días calendario reales de paper trading"`

`python3 harness/scripts/progress.py block --phase 16 --deliverable certificacion-200-trades --motivo "requiere 200 trades reales paper; no generar trades artificiales"`

`python3 harness/scripts/progress.py block --phase 16 --deliverable certificacion-2-regimenes --motivo "requiere evidencia de al menos 2 regímenes de mercado"`

- [ ] **Step 3: Run verification**

Run: `bash harness/scripts/evidence.sh 16 certification-tests -- uv run pytest harness/tests/test_paper_certification.py -q`

Expected: exit 0.

- [ ] **Step 4: Run gate check**

Run: `python3 harness/scripts/gate_check.py --phase 16`

Expected: FAIL/PENDING due to real elapsed certification thresholds, not implementation errors.

- [ ] **Step 5: Reindex graph and check coverage**

Run MCP `index_repository`, then `check_index_coverage` for touched files.

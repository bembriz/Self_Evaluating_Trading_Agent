# Memory Integration Embedding Dimension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align memory-repository integration fixtures with the product's fixed 384-dimensional pgvector contract.

**Architecture:** Change only the test fixture vectors and their versioned `embedding_space` identifier. The existing `vector(384)` migration, ORM model, FastEmbed provider, and repository code remain the source of truth and receive no changes.

**Tech Stack:** Python 3.12, pytest, SQLAlchemy async, PostgreSQL, pgvector, Docker Compose.

## Global Constraints

- Change only `tests/integration/test_memory_repository.py`.
- Use deterministic in-memory vectors of exactly 384 dimensions; do not download an embedding model.
- Keep the temporal anti-leakage and embedding-space isolation assertions unchanged.
- Do not alter Alembic migrations, ORM models, repository code, or the PostgreSQL schema.
- PostgreSQL remains local-only at `127.0.0.1:5433` under approved DP-005.
- Do not commit without explicit user authorization.

---

## File Structure

- Modify: `tests/integration/test_memory_repository.py` - replace incompatible four-element fixture vectors with reusable, deterministic 384-element vectors.

### Task 1: Correct the pgvector Test Fixtures

**Files:**
- Modify: `tests/integration/test_memory_repository.py:17-56`

**Interfaces:**
- Consumes: PostgreSQL schema contract `memory_items.embedding vector(384)` from migration `0004`.
- Produces: `_embedding(index: int) -> list[float]` and `SPACE = "fake|fake-e5|384"` for integration tests.

- [ ] **Step 1: Write the failing dimensional-contract assertions**

```python
DIMENSION = 384
SPACE = "fake|fake-e5|384"


def _embedding(index: int) -> list[float]:
    vector = [0.0] * DIMENSION
    vector[index] = 1.0
    return vector


def test_fixture_embedding_matches_pgvector_dimension() -> None:
    assert len(_embedding(0)) == DIMENSION
    assert _embedding(0)[0] == 1.0
    assert _embedding(0)[1] == 0.0
```

- [ ] **Step 2: Run the test to verify the current fixture is incompatible**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/integration/test_memory_repository.py -v`

Expected: FAIL with `expected 384 dimensions, not 4` when the current four-element vectors reach pgvector.

- [ ] **Step 3: Replace only the integration fixture vectors**

```python
DIMENSION = 384
SPACE = "fake|fake-e5|384"


def _embedding(index: int) -> list[float]:
    vector = [0.0] * DIMENSION
    vector[index] = 1.0
    return vector


async def test_save_and_search_with_temporal_filter(session: AsyncSession) -> None:
    repo = SqlAlchemyMemoryRepository(session)
    base = _embedding(0)
    await repo.save_memory(_item("m_pasada", 900, base))  # type: ignore[arg-type]
    await repo.save_memory(_item("m_futura", 2000, base))  # type: ignore[arg-type]
    hits = await repo.search_similar(base, k=10, decision_timestamp_ms=1000, embedding_space=SPACE)
    ids = [hit.memory.id for hit in hits if isinstance(hit, ScoredMemory)]
    assert ids == ["m_pasada"], f"leakage detectado: {ids}"
```

Use `_embedding(1)` and `"otro|modelo|384"` in the embedding-space isolation test.

- [ ] **Step 4: Run the memory integration suite**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/integration/test_memory_repository.py -v`

Expected: PASS, including temporal filtering, embedding-space isolation, and reflection roundtrip.

- [ ] **Step 5: Run all integration tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/integration -v`

Expected: PASS with PostgreSQL healthcheck green.

- [ ] **Step 6: Run quality checks and record evidence**

Run: `ruff check tests/integration/test_memory_repository.py && ruff format --check tests/integration/test_memory_repository.py`

Record the targeted integration test, integration suite, and quality checks through `harness/scripts/evidence.sh 16` as separate artifacts.

- [ ] **Step 7: Run the complete suite**

Run: `PYTHONPATH=src .venv/bin/python -m pytest`

Expected: PASS with no integration errors. Do not request the Phase 16 gate, which remains contingent on real paper-trading certification thresholds and UAT.

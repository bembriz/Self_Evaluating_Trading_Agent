# Memory Integration Embedding Dimension Design

## Objective

Make the PostgreSQL+pgvector memory-repository integration tests use embeddings
compatible with the product's fixed 384-dimensional vector contract.

## Scope

Only `tests/integration/test_memory_repository.py` changes. The migration,
SQLAlchemy model, FastEmbed provider, repository implementation, and database
schema remain unchanged.

## Design

The test module will define `DIMENSION = 384` and generate deterministic unit
vectors through a local helper. The base query vector uses index zero; the
alternative embedding-space vector uses index one. Both vectors therefore have
384 components, retain predictable cosine behavior, and continue proving the
temporal anti-leakage and embedding-space isolation queries.

The fixture embedding space becomes `fake|fake-e5|384`, reflecting the actual
shape while remaining a deterministic test-only provider identifier.

## Non-Goals

- No variable-dimension vector storage.
- No Alembic migration or schema alteration.
- No FastEmbed model download or network dependency.
- No change to production embeddings or persisted memory records.

## Validation

- Run `tests/integration/test_memory_repository.py` against PostgreSQL+pgvector.
- Run all integration tests against the migrated local test database.
- Run the complete test suite after integrations pass.
- Record each verification through the Phase 16 evidence wrapper.

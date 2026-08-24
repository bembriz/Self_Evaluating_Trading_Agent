# Fase 09 — Trading Memory / RAG: Plan de Implementación

> Ejecución en línea por el controlador (subagentes sin saldo). TDD por tarea.

**Goal:** Trading Memory con PostgreSQL+pgvector: EmbeddingProvider local, recuperación top-k por similitud coseno con filtrado temporal anti-leakage, reflexiones estructuradas y comparador LLM vs LLM+Memory preparado (PRD §32–35, §55).

**Architecture:** Puerto `EmbeddingProvider` + `MemoryRepository` en `application/ports`; dominio puro en `domain/memory` (TradingMemory enriquecido, Reflection, guards); adaptadores `infrastructure/embeddings/fastembed_provider.py`, `infrastructure/database/{models,memory_repository}` + migración Alembic 0004 con extensión `vector`.

## Global Constraints

- Dominio puro sin I/O ni frameworks; Pydantic solo infraestructura.
- Leakage (PRD §34): ninguna recuperación puede devolver items con `outcome_timestamp >= decision_timestamp`. Tests automáticos obligatorios.
- Embeddings: modelo `intfloat/multilingual-e5-small` (384 dims, PRD §33); espacio versionado.
- El embedding del texto se calcula SIEMPRE sobre contenido con outcome cerrado (nunca información futura).

## Tasks

### Task 1: Dominio memoria (enriquecido) + Reflection + guards
- Modify: `src/domain/memory/memory.py` (TradingMemory: añade `strategy_version`, `prompt_version`, `llm_model`, `experiment_id`, `action`, `confidence`, `pnl`, `embedding` ya existe)
- Create: `src/domain/memory/reflection.py` (`Reflection` frozen: id, trade_id?, result LOSS/WIN/BREAKEVEN, primary_error, lesson, future_condition, created_at_ms)
- Create: `src/domain/memory/guards.py` (`assert_no_leakage(items, decision_timestamp_ms)` filtra/lanza si item.outcome_timestamp_ms >= decision_ts)
- Test: `tests/test_memory_domain.py`

### Task 2: Puertos EmbeddingProvider + MemoryRepository
- Create: `src/application/ports/embeddings.py` (`EmbeddingProvider` @runtime_checkable: `model_name -> str`, `dimension -> int`, `embed(texts) -> list[list[float]]`)
- Create: `src/application/ports/memory_repository.py` (`MemoryRepository`: `save(item)`, `save_reflection(refl, embedding)`, `search(query_embedding, k, decision_timestamp_ms, ...) -> list[ScoredMemory]`, `count()`)
- Test: `tests/test_llm_ports2.py` → `tests/test_memory_ports.py` (fakes estructurales)

### Task 3: Migración pgvector + modelos ORM
- Modify: `src/infrastructure/database/models.py` (MemoryItemRecord vector(384) + índice HNSW coseno; ReflectionRecord)
- Create: `migrations/versions/0004_memory_pgvector.py` (upgrade: CREATE EXTENSION IF NOT EXISTS vector, tablas, índices; downgrade completo)
- Test: integration `tests/integration/test_memory_repository.py` (requiere PG; pendiente de entorno)

### Task 4: Repositorio pgvector con búsqueda + filtrado temporal
- Create: `src/infrastructure/database/memory_repository.py` (SQLAlchemy: insert, búsqueda `<=>` coseno top-k WHERE outcome_timestamp_ms < :decision_ts)
- Test: integration (pendiente entorno) + unit de la query builder si es extraíble

### Task 5: Adapter FastEmbed local
- Create: `infrastructure/embeddings/fastembed_provider.py` (`FastEmbedProvider(model_name="intfloat/multilingual-e5-small")`; lazy init; `EMBEDDING_MODEL_VERSION` versionado)
- Test: `tests/test_fastembed_provider.py` (fake/skip si no hay red; smoke real como evidencia)

### Task 6: Comparador LLM vs LLM+Memory (preparado)
- Create: `src/application/services/memory_comparison.py` (corre decisiones con memories=[] vs memories=recuperadas usando un provider dado; métricas de decisión)
- Test: `tests/test_memory_comparison.py` (con FakeProvider)
- Nota: ejecución real queda pendiente de DEEPSEEK_API_KEY (decisión del usuario)

## Verificación

```bash
uv run pytest tests --ignore=tests/integration --cov=src --cov-branch --cov-fail-under=90
uv run ruff check . && uv run ruff format --check .
uv run mypy src tests
```

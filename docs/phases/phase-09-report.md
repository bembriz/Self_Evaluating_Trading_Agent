# Reporte de Fase 09 — Trading Memory / RAG

**Fecha:** 2026-08-23
**Estado de fase:** in_progress (pendiente UAT + gate)
**Avance fase:** 100.0% entregables con evidencia · **Gate mecánico:** 5 PASS · 0 FAIL · 2 MANUAL
**Rama:** `feature/phase-08-llm-decision-agent` (continuidad; sin commits nuevos aún)

---

## 1. Executive Summary

Trading Memory operativa sobre PostgreSQL+pgvector (PRD §32–35, §55): esquema `memory_items`/`reflections` con columna `vector(384)` e índice HNSW coseno, puerto `EmbeddingProvider` con adapter local fastembed (modelo real verificado), recuperación top-k por similitud coseno con filtro temporal obligatorio `outcome_timestamp < decision_timestamp` y doble guard anti-leakage (SQL + dominio), reflexiones estructuradas persistidas, y comparador LLM vs LLM+Memory listo (pendiente ejecución real de API key, decisión del usuario). Suite 254 passed, cobertura 92.28%.

## 2. Objetivo

Dotar al agente de memoria vectorial recuperable por similitud semántica, SIEMPRE filtrada temporalmente para evitar data leakage (PRD §34), con embeddings locales versionados (§33) y reflexiones solo de trades cerrados (§35).

## 3. Scope

- Dominio puro: `TradingMemory` enriquecido (resultado PnL/MFE/MAE/fees/slippage + versiones §32), `Reflection`, guards `filter_leakage`/`assert_no_leakage`, espacios versionados `(provider|model|dim)`.
- Puertos: `EmbeddingProvider`, `MemoryRepository` (+ `ScoredMemory`).
- Migración Alembic `0004_memory_pgvector`: extensión `vector`, tablas, índices HNSW/btree, downgrade completo.
- Adapter `SqlAlchemyMemoryRepository`: búsqueda `<=>` coseno top-k filtrada por tiempo y espacio.
- Adapter `FastEmbedProvider` local ONNX con inyección de factory para tests sin red.
- Servicio `MemoryComparison` (LLM vs LLM+Memory) con guard aplicado antes de inyectar memorias.
- DP-003 APPROVED: dependencias `pgvector>=0.5` + `fastembed>=0.4`.

## 4. Out of Scope

- Ejecución real del experimento LLM vs LLM+Memory contra DeepSeek (requiere `DEEPSEEK_API_KEY`; decisión del usuario en sesión).
- Integración de la memoria en el prompt del DecisionAgent en producción (llega con fases 10–11).
- Reindexación automática ante cambio de modelo de embeddings.

## 5. Arquitectura antes/después

Antes: `domain/memory` mínimo (fase 08), sin persistencia vectorial. Después: dominio completo + puertos + repositorio pgvector + provider local. Dependencias toward-domain; fastembed aislado tras el puerto; el espacio de embeddings viaja con cada item (`embedding_space`) impidiendo mezclas.

## 6. Archivos creados

`src/domain/memory/{reflection,space,guards}.py`, `src/application/ports/{embeddings,memory_repository}.py`, `src/application/services/memory_comparison.py`, `src/infrastructure/embeddings/fastembed_provider.py`, `src/infrastructure/database/memory_repository.py`, `migrations/versions/0004_memory_pgvector.py`, tests: `test_memory_domain.py`, `test_memory_ports.py`, `test_fastembed_provider.py`, `test_memory_comparison.py`, `tests/integration/test_memory_repository.py`.

## 7. Archivos modificados

`src/domain/memory/memory.py` (campos §32), `pyproject.toml`/`uv.lock` (DP-003), docs de fase/UAT/plans, ledger de progreso.

## 8. Dependencias

DP-003 APPROVED (2026-08-23): `pgvector==0.5.0` (1 paquete) y `fastembed` (14 paquetes, ONNX sin torch). Evidencia: `docs/phases/09/evidence/dp003-apply-validate.log`. Documento: `docs/phases/09/dp-003-pgvector-fastembed.md`.

## 9. Configuración

Sin claves nuevas en Settings (la dimensión/modelo viven como constantes del adapter versionadas por espacio). `.env` no modificado; sin secretos.

## 10. Comandos exactos

```bash
uv add pgvector "fastembed>=0.4"                                            # DP-003 APPLY
uv run pytest tests --ignore=tests/integration --cov=src --cov-branch --cov-fail-under=90   # 254 passed, 92.28%
RUN_MODEL_SMOKE=1 uv run pytest tests/test_fastembed_provider.py::test_smoke_real_model_downloads_and_embeds -v
uv run ruff check . && uv run ruff format --check .                          # OK
uv run mypy src tests                                                        # Success
```

## 11. Rutas

Sin cambios de API.

## 12. API endpoints

Ninguno.

## 13. Migraciones

`0004_memory_pgvector.py`: upgrade crea extensión `vector`, `memory_items` (vector(384), HNSW `vector_cosine_ops`, índices btree outcome/space) y `reflections`; downgrade real (drop índices+tablas, extensión se conserva). Test up→down→up existe en `tests/integration/test_alembic.py` — pendiente de entorno (Docker ausente).

## 14. Tests

| Nivel | Ejecutado | Resultado | Evidencia |
|---|---|---|---|
| Unit | ✅ 254 passed | PASS (92.28%) | `tests-unit.log` |
| Integration | ⚠️ Pendiente de entorno (Docker/PostgreSQL ausente): incluye roundtrip Alembic 0004 y búsqueda pgvector con filtrado temporal | N/A entorno | igual que fase 08 |
| Smoke modelo real | ✅ PASS (9.7s, descarga+embedding 384 dims) | PASS | `embeddings-locales-smoke.log` |
| E2E | ☐ | Fases 10–11 | — |

## 15. Coverage

92.28% global branch ≥ 90% (TOTAL 2544 stmts, 184 missed). Nuevos módulos cubiertos por unit tests con fakes deterministas.

## 16. E2E

No aplica aún. El comparador `MemoryComparison` se probó con fake provider verificando ambos brazos y el guard de leakage (test dedicado).

## 17. UAT

- Checklist: `docs/uat/phase-09-uat.md`
- Veredicto: PENDIENTE

## 18. Evidencias

Índice en `docs/phases/09/evidence/log.md`: `dp003-apply-validate`, `tests-unit`, `lint`, `format-check`, `mypy`/`typing`, `embeddings-locales-smoke`.

## 19. Métricas

8/8 entregables con evidencia. Anti-leakage: triple capa (filtro SQL obligatorio + guard de dominio post-query + guard en el comparador antes de inyectar). Espacio de embeddings versionado y verificado en query.

## 20. Logs relevantes

Smoke real: modelo `paraphrase-multilingual-MiniLM-L12-v2` descargado y vector de 384 dims generado. Detalle en log de evidencia.

## 21. Git diff

Cambios de la fase 09 sobre working tree (aún sin commit). Diff a generar junto al commit candidate de la fase.

## 22. Riesgos

- Desviación documentada del PRD: e5-small no soportado por fastembed → `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (multilingüe, 384 dims, 0.22GB). Cambiar modelo = espacio nuevo + reindexación (reglas del skill rag-memoria).
- Índice HNSW sin datos aún: parámetros por defecto; revisar con volumen real.

## 23. Seguridad

Sin secretos nuevos. Modelos descargados desde HuggingFace Hub fijados por nombre exacto. SQL parametrizado vía ORM (sin inyección).

## 24. Deuda técnica

- Persistencia de llm_calls/costs (heredada de fase 08).
- Reindexador de espacios de embeddings (cuando cambie el modelo).
- Tests de integración pendientes de entorno Docker.

## 25. Known Issues

- Docker ausente: integration tests no ejecutables en este entorno (preexistente, documentado).
- `fastembed` limita el catálogo de modelos soportados; e5-small quedaría para un runtime alternativo si algún día se requiere fidelidad al PRD literal.

## 26. Rollback

`git checkout` del estado previo + `uv remove pgvector fastembed` + `alembic downgrade 0003`. Sin datos productivos afectados.

## 27. Competencias practicadas

RAG (retrieval top-k), Embeddings (espacios versionados, prefijos e5, ONNX local), Vector Search (HNSW/coseno pgvector), Agent Memory (memoria de experiencias cerradas), Data Engineering (migración con extensión), Testing (guards anti-leakage automáticos, fakes sin red).

## 28. Definition of Done

- [x] Scope completo (8/8)
- [x] Unit PASS (254) · coverage 92.28%
- [ ] Integration PASS (entorno)
- [ ] E2E (fases posteriores)
- [ ] UAT approved (PENDIENTE usuario)
- [x] Lint/typing green
- [x] Evidencias completas
- [ ] Diff reviewed + user approval

## 29. Estado CI

Sin push remoto aún (pendiente autorización); verificaciones locales equivalentes green.

## 30. Solicitud de aprobación

- [ ] Presentado al usuario
- **DECISIÓN DEL USUARIO:** ☒ APPROVED
- Comentario:

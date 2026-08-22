---
name: rag-memoria
description: Usar al implementar la Trading Memory con PostgreSQL+pgvector, el EmbeddingProvider, recuperación por similitud con filtrado temporal, o almacenamiento/recuperación de reflexiones (PRD §32-33, §35)
---

# rag-memoria — Memoria vectorial del agente

## Propósito

Memoria operativa: decisiones pasadas + resultados + reflexiones, recuperables por similitud semántica y SIEMPRE filtradas temporalmente para evitar leakage. Espacios de embeddings versionados.

## Cuándo usar

- Modelar `memory_items` (decisión, state, features, régimen, resultado, PnL, MFE/MAE, fees, slippage, reflexión, embedding, versiones de estrategia/prompt/modelo/experimento).
- Implementar `EmbeddingProvider` local (`intfloat/multilingual-e5-small`) y futuro OpenAI.
- Recuperación top-k similar + filtro `outcome_timestamp < decision_timestamp`.
- Insertar reflexiones solo cuando el trade terminó.

**Cuándo NO:** decidir qué se memoriza (Evaluation/Reflection); contratos LLM (llm-provider-pattern).

## Reglas duras

1. **Filtro temporal obligatorio** en toda query de memoria (data-leakage): la similitud NUNCA viaja sola.
2. Cambiar modelo de embeddings ⇒ reindexar ese espacio; espacio versionado por (provider, model, dim).
3. Reflexión entra a memoria únicamente con outcome cerrado.
4. Embeddings calculados con el provider declarado en el experimento (reproducibilidad §38).

## Checklist de implementación

1. Esquema pgvector con dimensión correcta e índice apropiado (postgres-pgvector-alembic).
2. Provider local sin red en tests (modelo cacheado); fake determinista para unit/integration.
3. Query tipo: `ORDER BY embedding <=> :q LIMIT k` + `WHERE outcome_ts < :decision_ts AND embedding_space = :v`.
4. Tests: similitud esperada en corpus pequeño etiquetado; leakage test garantiza que memorias futuras no aparecen jamás.
5. Métricas: memory hits, similarity distribution (PRD §46).
6. Comparativa obligatoria Fase 09: LLM vs LLM+Memory sobre mismo dataset.

## Errores comunes

- Reindexar "en sitio" mezclando espacios de versiones distintas.
- k grande sin diversidad → sesgo de confirmación en el prompt.
- Guardar embeddings sin metadatos de versión.

## Referencias

- PRD §32–35, §46. Skills: data-leakage, postgres-pgvector-alembic, llm-provider-pattern.

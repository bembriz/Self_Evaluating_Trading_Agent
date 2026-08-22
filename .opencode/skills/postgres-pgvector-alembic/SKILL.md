---
name: postgres-pgvector-alembic
description: Usar al modelar entidades de PostgreSQL (PRD §55), escribir migraciones Alembic, integrar SQLAlchemy 2.x, crear índices/consultas pgvector, o probar upgrades/downgrades
---

# postgres-pgvector-alembic — Persistencia del producto

## Propósito

Esquema fiel al modelo PRD §55, migraciones seguras con tests up/down, ORM sin pelear con SQL explícito cuando convenga, y recuperación vectorial eficiente con pgvector.

## Cuándo usar

- Crear/modificar tablas: market_candles, decisions, orders, fills, trades, trade_outcomes, reflections, memory_items, strategies/prompts/experiments versions, llm_calls/costs, risk_configs, dataset_manifests, approvals, audit_events.
- Migraciones nuevas o revisión de existentes.
- Consultas de similitud (memory_items.embedding) y analytics cuantitativo.

**Cuándo NO:** decisiones sobre qué datos almacenar (eso es dominio/diseño); queries one-off de análisis.

## Convenciones del proyecto

- SQLAlchemy 2.x estilo tipado (`Mapped[...]`), sesiones por request/task; engine único.
- Alembic obligatorio para TODO cambio de esquema — nunca DDL manual en producción.
- Toda migración: `upgrade()` + `downgrade()` + test integration que ejecute ambos.
- Timestamps UTC con timezone; claves naturales donde aplique (symbol+timeframe+open_time).
- pgvector: columna `vector(dim)` según embedding versionado; índice IVFFlat/HNSW tras volumen; filtrado temporal SIEMPRE acompañando similitud (`outcome_timestamp < decision_timestamp`, ver data-leakage).
- Particionado por rango temporal en tablas grandes si el volumen lo justifica (no antes).
- Analytics pesados: SQL explícito permitido (PRD §57) documentado en repositorio de queries.

## Checklist de migración nueva

1. Modelo + migration generada desde autogenerate revisada A MANO.
2. downgrade() real (no pass).
3. Test up→down→up en DB efímera (testing-integration).
4. Datos existentes: estrategia de backfill definida.
5. Índices justificados por patrón de consulta real.
6. Evidencia de corrida + mención en reporte §13.

## Errores comunes

- Editar esquema productivo manualmente (prohibido PRD §56).
- Migraciones irreversibles.
- Búsqueda vectorial sin filtro temporal (riesgo leakage).

## Referencias

- PRD §55–57. Skills: testing-integration, data-leakage, rag-memoria. Global: database-sql-standards.

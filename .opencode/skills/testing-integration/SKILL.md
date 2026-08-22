---
name: testing-integration
description: Usar cuando dos o más componentes reales deban probarse juntos (FastAPI↔PostgreSQL↔pgvector, adapters↔fixtures grabados, Alembic up/down, Decision Agent↔fake LLM), incluyendo edge cases y recuperación de errores (PRD §72)
---

# testing-integration — Integración con componentes reales

## Propósito

Verificar que las piezas integradas funcionan juntas con servicios reales donde importa (PostgreSQL/pgvector/Alembic) y con dobles controlados donde no (LLM fake, mensajes WS grabados de Bybit).

## Cuándo usar

- FastAPI ↔ PostgreSQL ↔ pgvector.
- Market Adapter ↔ fixtures grabados (mensajes reales capturados).
- Risk Engine ↔ Execution Engine.
- Alembic upgrade/downgrade completo.
- Edge cases: desconexión a mitad de snapshot, JSON inválido del LLM, transacción abortada.

**Cuándo NO:** lógica pura (→ testing-unit); ciclo end-to-end completo (→ testing-e2e).

## Entradas → Salidas

- **Entradas:** componentes implementados + sus unit tests verdes; servicios locales (docker compose) cuando aplican.
- **Salidas:** suite integration verde + evidencia; fixtures nuevos versionados si se grabaron.

## Convenciones del proyecto

- Servicios reales vía `docker compose` (requieren gate infra-control la primera vez por fase).
- Externos no deterministas SIEMPRE dobles: `FakeLLMProvider`, repositorios en memoria solo para tests unitarios (aquí usa DB real).
- Fixtures grabados bajo `tests/fixtures/` con esquema documentado; nunca dependas de red externa en CI.
- Cada test integration marca `@pytest.mark.integration`.
- Alembic: todo migración exige test upgrade Y downgrade.

## Checklist por caso

1. Estado inicial conocido (migraciones frescas o fixture de datos).
2. Camino feliz + al menos un edge case + un caso de error.
3. Recuperación: qué pasa si el servicio cae a mitad (timeout, retry, estado consistente).
4. Limpieza idempotente (no depender de orden).
5. Evidencia registrada con evidence.sh.

## Errores comunes

- Mockear la base de datos: entonces NO es integration.
- Tests que solo pasan con red real: prohibido en CI.
- No probar rollback de migraciones.

## Referencias

- PRD §72. Globales: database-sql-standards, error-handling-resilience, api-client-standards.

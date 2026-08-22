---
name: fastapi-standards
description: Usar al crear o modificar endpoints/routers/schemas/middleware de la API FastAPI del producto, definir contratos Pydantic v2, o proteger endpoints administrativos (PRD §54, §52-53)
---

# fastapi-standards — API FastAPI del producto

## Propósito

API desacoplada de la interfaz web, contratos explícitos con Pydantic v2, endpoints admin protegidos, errores consistentes y observables.

## Cuándo usar

- Añadir endpoints del contrato PRD §54 (`/health`, `/ready`, `/api/v1/*`).
- Modelar request/response schemas.
- Proteger acciones sensibles (kill-switch, trading/mode) con confirmación + audit_event.
- Integrar HTMX/Jinja sin acoplar lógica a vistas.

**Cuándo NO:** consumo de APIs externas (usa api-client-standards para Bybit/LLM).

## Convenciones del proyecto

- Routers por dominio bajo `src/interfaces/api/`; versionado `/api/v1`.
- Schemas Pydantic v2 separados de entidades de dominio (mapeo explícito).
- Respuestas de error uniformes: `{"error": {"code", "message", "details"}}`.
- Endpoints administrativos: dependencia de auth (rol operator) + confirmación + `audit_events`.
- Nunca exponer secretos ni configuración interna sensible en respuestas.
- Async por defecto para I/O (Bybit/DB); sync permitido en cómputo CPU-bound vía worker.
- Cada endpoint: test integration (happy/error/auth) y latencia observable (Prometheus).

## Contrato mínimo inicial (PRD §54)

GET /health · GET /ready · GET /api/v1/system/state · GET /api/v1/market/{eth,btc} · GET /api/v1/{decisions,trades,positions} · GET /api/v1/analytics/performance · GET /api/v1/experiments[/{id}] · GET /api/v1/live/readiness · POST /api/v1/kill-switch · POST /api/v1/trading/mode

## Checklist por endpoint nuevo

1. ¿Está en el contrato PRD o hay justificación + ADR?
2. Schema request/response definido y validado.
3. Auth/protección según sensibilidad.
4. Test integration con DB real (testing-integration).
5. Métricas de latency/count registradas.
6. Documentado en reporte de fase §12.

## Errores comunes

- Lógica de negocio en routers: pertenece a application/services.
- Devolver modelos ORM crudos: mapear a schemas.
- POST sensible sin audit_event.

## Referencias

- PRD §53–54. Skills: testing-integration, arquitectura-hexagonal, logging-observability.

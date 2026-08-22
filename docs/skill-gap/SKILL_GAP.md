# Informe de Skill Gap — Arnés Fase 00

**Fecha:** 2026-08-22
**Método:** Escaneo directo del inventario real instalado en esta máquina:
- Globales: `~/.config/opencode/skills/` (14 skills)
- Superpowers: `~/.cache/opencode/packages/superpowers@…/skills/` (14 skills)

**Regla:** reutilizar antes de crear; crear solo lo que ningún skill existente cubre.

---

## 1. Inventario real encontrado

### Skills globales (14)

| Skill | Cobertura | ¿Relevante aquí? |
|---|---|---|
| api-client-standards | Consumo de HTTP/REST/GraphQL y servicios externos | Sí — complemento para Bybit |
| code-quality | Calidad al escribir/modificar código de producción | Sí |
| configuration-environments | Config por entorno, credenciales, feature flags | Sí |
| database-sql-standards | BD relacional / SQL | Parcial — falta stack concreto (SQLAlchemy 2.x/Alembic/pgvector) |
| data-pipeline-quality | ETL/ELT, ingesta batch/streaming | Sí — Fases 03–05 (market data) |
| docker-standards | Docker/Compose/OCI | Sí |
| documentation-standards | Documentación de repositorio | Sí |
| error-handling-resilience | Fallos de red/servicios/concurrencia | Sí — reconexiones WS, fail-safe LLM |
| git-safety-guardrails | Operaciones Git seguras | Sí |
| logging-observability | Diagnóstico operativo, logs/métricas | Sí |
| project-bootstrap | Estructura inicial de proyectos | Referencia |
| python-uv | Proyectos Python con uv | Sí |
| security-secrets | Credenciales/API keys/.env/CI secrets | Sí |
| terraform-standards | IaC Terraform/OpenTofu | **No aplica** (sin IaC en este proyecto) |

### Skills superpowers (14)

| Skill | Uso en el arnés |
|---|---|
| brainstorming | Diseño previo a features (ya usado para este arnés) |
| test-driven-development | Metodología base de toda implementación |
| systematic-debugging | Depuración disciplinada de bugs/fallos de tests |
| writing-plans / executing-plans | Planes por fase con checkpoints |
| subagent-driven-development / dispatching-parallel-agents | Tareas independientes por fase |
| requesting-code-review / receiving-code-review | Revisión cruzada implementación↔validación |
| verification-before-completion | Obligatoria antes de declarar gates PASS |
| using-git-worktrees / finishing-a-development-branch | Aislamiento e integración de ramas |
| writing-skills | **Metodología para crear las skills nuevas de este catálogo** |
| using-superpowers | Orquestador general |

## 2. Matriz de brechas (dominios requeridos → resolución)

| # | Dominio requerido | Existente que lo cubre | Resolución |
|---|---|---|---|
| 1 | Arquitectura (hexagonal, ADR) | — | **CREAR** `arquitectura-hexagonal` |
| 2 | FastAPI | — (api-client-standards es lado consumidor) | **CREAR** `fastapi-standards` |
| 3 | PostgreSQL (+pgvector/Alembic) | database-sql-standards (parcial) | **CREAR** `postgres-pgvector-alembic` (stack concreto; la global sigue aplicando) |
| 4 | Docker | docker-standards | REUTILIZAR |
| 5 | CI/CD (GitHub Actions) | — | **CREAR** `cicd-github-actions` |
| 6 | Seguridad/secrets | security-secrets | REUTILIZAR |
| 7 | Observabilidad | logging-observability | REUTILIZAR |
| 8 | Git (flujo + aprobaciones) | git-safety-guardrails + superpowers | REUTILIZAR + **CREAR** `flujo-commits` (Commit Candidate Report §66) |
| 9 | Unit Testing | superpowers:test-driven-development (metodología) | **CREAR** `testing-unit` (gates cobertura ≥90%, evidencia) |
| 10 | Integration Testing | — | **CREAR** `testing-integration` |
| 11 | E2E | — | **CREAR** `testing-e2e` |
| 12 | UAT/HITL | — | **CREAR** `uat-hitl` |
| 13 | Evidencia de pruebas | — | **CREAR** `gestion-evidencias` |
| 14 | LLM (provider pattern) | — | **CREAR** `llm-provider-pattern` |
| 15 | RAG/memoria | — | **CREAR** `rag-memoria` |
| 16 | Bybit | — (api-client-standards como complemento) | **CREAR** `bybit-integration` |
| 17 | Backtesting | — | **CREAR** `backtesting` |
| 18 | Risk Engine | — | **CREAR** `risk-engine` |
| 19 | Data leakage | — | **CREAR** `data-leakage` |
| 20 | Walk-forward | — | **CREAR** `walk-forward-validacion` |
| 21 | Validación estadística | — | **CREAR** `validacion-estadistica` |
| 22 | Reporting de fases | documentation-standards (parcial) | **CREAR** `reporting-fases` (30 secciones §76 + PDF) |
| 23 | Release readiness | — | **CREAR** `release-readiness` |
| 24 | Control infraestructura/deps | — | **CREAR** `infra-control` (DISCOVER→…→EVIDENCE) |
| 25 | codebase-memory-mcp | — | **CREAR** `codebase-memory-mcp` |

**Totales: reutilizar 11 globales + 10 superpowers · crear 22 nuevas.**

## 3. Catálogo final propuesto (G1)

Las 22 skills de la columna CREAR, en `.opencode/skills/<nombre>/SKILL.md` (+ templates/examples cuando aporten), todas en español, siguiendo la metodología de `superpowers:writing-skills`.

Agrupación funcional:

- **Gobierno:** flujo-commits, infra-control, gestion-evidencias, reporting-fases, uat-hitl
- **Testing:** testing-unit, testing-integration, testing-e2e
- **Plataforma:** arquitectura-hexagonal, fastapi-standards, postgres-pgvector-alembic, cicd-github-actions, release-readiness, codebase-memory-mcp
- **Dominio trading:** bybit-integration, backtesting, risk-engine, data-leakage, walk-forward-validacion, validacion-estadistica
- **IA:** llm-provider-pattern, rag-memoria

## 4. Notas

- Ninguna skill nueva duplica una existente; donde hay solapamiento parcial (database-sql-standards, api-client-standards, documentation-standards), la nueva referencia explícitamente a la global y solo añade lo específico del proyecto.
- La instalación de codebase-memory-mcp NO ocurre en G1: se gestiona vía Dependency Proposal gated (skill `codebase-memory-mcp`, requisito #8 del PRD).

# Diseño del Arnés Agéntico — Fase 00 (Governance & Agent Bootstrap)

**Versión:** 1.0
**Fecha:** 2026-08-22
**Estado:** Aprobado por el usuario
**Producto objetivo:** Self-Evaluating Trading Agent — ETH/USDT (ver `docs/PRD — Self-Evaluating Trading Agent.md`)
**Arnés principal:** OpenCode (AGENTS.md + skills + enforcement técnico)

---

## 1. Propósito

Construir el arnés que gobierne el desarrollo del producto descrito en el PRD **por fases, con aprobación humana explícita**, sin adelantar funcionalidad del producto. El arnés **ES la Fase 00** del roadmap del PRD.

Requisitos de origen (del usuario): checkpoints con GATE por fase; progreso/ETA objetivos; testing exhaustivo (Unit/Integration/E2E/UAT); control de infraestructura; catálogo profesional de skills; integración codebase-memory-mcp; Git con autorización obligatoria; separación de responsabilidades; complejidad mínima; propósito educativo.

## 2. Decisiones confirmadas

| # | Decisión | Elección |
|---|---|---|
| 1 | Relación arnés/Fase 00 | El arnés ES la Fase 00 |
| 2 | Ubicación de skills nuevas | `.opencode/skills/` del proyecto, versionadas en Git |
| 3 | Idioma | Todo en español (código y commits en inglés por convención técnica) |
| 4 | % de avance | Ledger `progress.yaml`; fases iguales (100/19), entregables iguales dentro de fase; gates binarios; sin gate → fase aporta máx. 90% de su peso |
| 5 | ETA | Velocidad observada (entregables/día) + rango proyectado (±30% hasta acumular varianza real) |
| 6 | Conversor PDF | WeasyPrint como dev-dependency vía uv (requiere Dependency Proposal autorizada) |
| 7 | Remoto | El usuario crea el repo GitHub; CI se activa al primer push autorizado |
| 8 | codebase-memory-mcp | Skill + Dependency Proposal ahora; instalación gated durante ejecución |
| 9 | Calidad scripts arnés | Pragmática: pytest + ~80% cobertura |
| 10 | Enforcement | Instrucciones (AGENTS.md/skills) + permission rules en `opencode.json` |
| 11 | Fixtures/simuladores | Solo patrones + fixtures ejemplo; simuladores reales los construye cada fase |
| 12 | Gates internos arnés | G1 (catálogo) → G2 (núcleo) → G3 (cierre) |

## 3. Arquitectura

```text
Self-Evaluating_Trading_Agent/
├── AGENTS.md                      # Orquestador: ciclo operativo por fase, routing a skills,
│                                  # reglas duras PRD §84, definición de gates y DoD
├── opencode.json                  # Hard enforcement (permission rules ask/deny)
├── README.md                      # Entrada humana + guía de uso del arnés
├── .gitignore / .env.example      # datasets/, .env, evidencia cruda excluidos
│
├── .opencode/skills/              # Catálogo especializado en español
│   └── <nombre-skill>/SKILL.md    # Propósito, entradas/salidas, checklist,
│                                  # permitido/prohibido, templates/, examples/
│
├── harness/
│   ├── scripts/                   # Python gestionado con uv, sin frameworks:
│   │   ├── progress.py            #   Ledger → % objetivo, tareas, bloqueos, ETA (rango)
│   │   ├── gate_check.py          #   Valida DoD fase vs evidencias → PASS/FAIL/MANUAL
│   │   ├── evidence.sh            #   Envuelve comandos → log comando+exit+artefacto
│   │   ├── gen_report.py          #   Reporte fase desde plantilla+datos verificados
│   │   ├── gen_pdf.py             #   MD → PDF (WeasyPrint)
│   │   └── new_phase.py           #   Scaffold: entrada ledger + dirs + esqueleto reporte
│   ├── state/progress.yaml        # LEDGER versionado = única fuente del % de avance
│   ├── templates/                 # reporte-fase, uat-checklist, dependency-proposal,
│   │                              # commit-candidate, adr
│   └── tests/                     # pytest de los scripts (~80% cobertura)
│
└── docs/
    ├── design/harness-design.md   # Esta especificación
    ├── skill-gap/SKILL_GAP.md     # Informe Skill Gap real (G1)
    ├── phases/                    # phase-XX-report.md (+pdf) + evidence/ por fase
    ├── uat/                       # Instructivos UAT por fase
    └── adr/                       # ADR-0001-harness.md, ADRs posteriores
```

### Separación de responsabilidades

Implementar ≠ Probar ≠ Validar ≠ Aprobar:

- La skill que implementa código no ejecuta `gate_check` sobre su propio trabajo.
- La validación objetiva corre en scripts deterministas (`gate_check.py`, `progress.py`).
- La aprobación es siempre humana (gates MANUAL).

## 4. Catálogo de skills

### 4.1 Reutilizadas (mapping documentado en SKILL_GAP.md)

Globales: python-uv, docker-standards, security-secrets, logging-observability, configuration-environments, error-handling-resilience, database-sql-standards, code-quality, documentation-standards, git-safety-guardrails, api-client-standards.
Superpowers: test-driven-development, systematic-debugging, writing-plans, executing-plans, requesting-code-review, receiving-code-review, verification-before-completion.

### 4.2 Nuevas a crear (22, sujeto a confirmación en G1)

| # | Skill | Dominio cubierto |
|---|---|---|
| 1 | arquitectura-hexagonal | arquitectura |
| 2 | fastapi-standards | FastAPI |
| 3 | postgres-pgvector-alembic | PostgreSQL |
| 4 | cicd-github-actions | CI/CD |
| 5 | testing-unit | Unit Testing |
| 6 | testing-integration | Integration Testing |
| 7 | testing-e2e | E2E |
| 8 | uat-hitl | UAT/HITL |
| 9 | gestion-evidencias | evidencia verificable |
| 10 | reporting-fases | reporting |
| 11 | release-readiness | release readiness |
| 12 | llm-provider-pattern | LLM |
| 13 | rag-memoria | RAG/memoria |
| 14 | bybit-integration | Bybit |
| 15 | backtesting | backtesting |
| 16 | risk-engine | Risk Engine |
| 17 | data-leakage | data leakage |
| 18 | walk-forward-validacion | walk-forward |
| 19 | validacion-estadistica | validación estadística |
| 20 | codebase-memory-mcp | integración MCP |
| 21 | infra-control | flujo infraestructura DISCOVER→…→EVIDENCE |
| 22 | flujo-commits | Commit Candidate Report |

Cada skill nueva incluirá: propósito, cuándo usarla / cuándo no, entradas y salidas, checklist paso a paso, acciones permitidas y prohibidas, plantillas reutilizables y ejemplos.

## 5. Flujos de control

### 5.1 Gate de fase (producto)

1. Agente completa el scope de la fase usando las skills correspondientes.
2. `gate_check.py --phase XX`: valida mecánicamente todo lo verificable (tests PASS registrados en evidencia, coverage ≥90 desde coverage.json, lint, typing, entregables presentes) → checklist PASS/FAIL/MANUAL.
3. Solo con todo verde: `gen_report.py` produce `docs/phases/phase-XX-report.md` (30 secciones PRD §76); PDF al solicitar cierre.
4. Skill `uat-hitl` genera instructivo UAT; el usuario lo ejecuta y reporta resultado.
5. Aprobación humana → actualización del ledger via script → siguiente fase o ciclo de fixes.
6. Sin USER APPROVAL no inicia la siguiente fase (PRD §78).

### 5.2 Gates internos del arnés

- **G1:** escaneo real de skills globales → `SKILL_GAP.md` + catálogo final → aprobación del usuario.
- **G2:** núcleo operativo: opencode.json + AGENTS.md + harness/scripts + templates + progress.yaml + tests pasando + demo sandbox → aprobación.
- **G3:** skills restantes + Dependency Proposal codebase-memory-mcp + README + reporte ejecutivo final (MD+PDF) + UAT del arnés → **aprobación final = FASE 00 DONE**.

### 5.3 Control de infraestructura (skill infra-control)

`DISCOVER` (solo lectura) → `PLAN/DRY-RUN` (`uv add --dry-run`, `docker compose config`) → `REPORT` (Dependency Proposal PRD §11) → **USER GATE** → `APPLY` → `VALIDATE` (healthchecks/tests) → `EVIDENCE`.
Antes del gate solo comandos read-only/dry-run.

### 5.4 Git con autorización (skill flujo-commits)

Permitido sin pedir: crear ramas (feature/*, fix/*, chore/*), editar, testear, staging, generar reportes.
Requiere autorización explícita: `git commit/push/merge/tag/release`.
Antes de pedirla: Commit Candidate Report completo (PRD §66). Primer commit = scaffolding del arnés.

### 5.5 Enforcement técnico (opencode.json)

- `ask`: git commit/push/merge/tag, gh release, uv add, pip install, docker pull, docker compose up/down.
- `deny`: comandos destructivos (p. ej. rm -rf sobre rutas raíz).
- Esquema exacto verificado contra docs oficiales de OpenCode durante construcción (G2).

## 6. Ledger, % y ETA

`harness/state/progress.yaml`:
- 19 fases (00–18), peso igual 100/19; entregables del PRD §79 con peso igual dentro de fase.
- Estados: fase `pending|in_progress|gate_requested|done`; entregable `pending|done|blocked`.
- Mutación solo mediante scripts y solo con evidencia adjunta (ruta + hash o salida).
- Gates binarios; cap del 90% por fase sin gate aprobado.
- `time_log` por evento → velocidad real → ETA en rango.
- Sección `blockers`.

Salida de `progress.py`: tabla Markdown (% global y por fase, terminadas/pendientes/bloqueadas, ETA, bloqueos). El agente nunca edita números a mano.

## 7. Integración codebase-memory-mcp

Skill dedicada documenta: instalación gated (Dependency Proposal al inicio de ejecución), registro en opencode.json, flujo obligatorio por fase `Index → Understand → Impact Analysis → Implement → Re-index → Verify`, y análisis de blast radius pre-commit (checklist integrado en flujo-commits). Hasta su instalación: sustituto provisional grep/glob + lectura directa (deuda temporal anotada).

## 8. Testing

- Scripts del arnés: pytest, cobertura objetivo ~80% (`uv run pytest harness/tests --cov=harness/scripts --cov-fail-under=80`).
- Convenciones para producto (sin implementar): fixtures ejemplo grabados (mensajes WS Bybit, salidas LLM JSON), plantillas conftest/fakes, marcadores pytest (`unit/integration/e2e/uat`), patrón evidence.sh.
- Simuladores ejecutables reales: los construye cada fase bajo estas convenciones.
- Verificación del arnés: tests + demo sandbox (fase ficticia recorriendo ledger→gate_check→reporte→PDF) + UAT instructivo ejecutado por el usuario en G3.

## 9. Criterios de aceptación del arnés (= DoD Fase 00)

1. Estructura completa creada y versionable.
2. SKILL_GAP.md real con mapping y catálogo final aprobado en G1.
3. Núcleo operativo funcionando con tests ≥80% (G2).
4. Skills nuevas creadas según catálogo aprobado (G3).
5. Dependency Proposal de codebase-memory-mcp lista para autorización.
6. Reporte ejecutivo final MD+PDF.
7. Instructivo UAT ejecutado por el usuario.
8. **Aprobación final del usuario = FASE 00 DONE.**

Fuera de alcance del arnés: cualquier componente funcional del trading agent (market data, features, LLM runtime, risk engine, dashboard, etc.) — pertenecen a Fases 01–18.

## 10. Competencias practicadas (educativo)

Git (trunk-based + approvals), Agentic Development (skills/orquestación/enforcement), Engineering Governance (gates/evidencia/DoD), Testing Automation (unit/integration/E2E/UAT design), Documentation as Code, Developer Experience.

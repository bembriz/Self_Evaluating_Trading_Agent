# AGENTS.md — Orquestador del Arnés · Self-Evaluating Trading Agent

> **Qué es:** reglas operativas que gobiernan cómo el agente (OpenCode) desarrolla este proyecto.
> **Qué NO es:** código del producto ni documentación funcional (eso vive en `docs/` y en las skills).
>
> **Fuente de verdad del producto:** [`docs/PRD — Self-Evaluating Trading Agent.md`](docs/PRD%20—%20Self-Evaluating%20Trading%20Agent.md)
> **Diseño del arnés:** [`docs/design/harness-design.md`](docs/design/harness-design.md)

---

## 1. Principio rector

Desarrollar por fases con **aprobación humana explícita entre fases**, evidencia verificable en cada paso y complejidad mínima. El agente implementa; **los scripts validan; el usuario aprueba.**

---

## 2. Mapa de fases (PRD §79)

| Fase | Título | Estado |
|---|---|---|
| 00 | Governance & Agent Bootstrap (**= este arnés**) | in_progress |
| 01 | Python Project Foundation | pending |
| 02 | PostgreSQL & Application Skeleton | pending |
| 03 | Historical Market Data | pending |
| 04 | Real-Time Market Data | pending |
| 05 | Feature Engine & Market State | pending |
| 06 | Backtesting & Deterministic Baseline | pending |
| 07 | ML Baseline | pending |
| 08 | LLM Decision Agent | pending |
| 09 | Trading Memory / RAG | pending |
| 10 | Risk & Paper Execution | pending |
| 11 | Evaluation & Reflection | pending |
| 12 | Bybit Testnet | pending |
| 13 | Dashboard & Observability | pending |
| 14 | Robustness Evaluation | pending |
| 15 | Local Release Candidate | pending |
| 16 | Paper Trading Certification | pending |
| 17 | LIVE Readiness Review | pending |
| 18 | Cloud Evaluation | pending |

El estado oficial NO se edita aquí: lo calcula `harness/scripts/progress.py`.

---

## 3. Ciclo operativo obligatorio por fase

```text
1. SCAFFOLD    python3 harness/scripts/new_phase.py --phase XX
2. ENTENDER    codebase-memory-mcp: Index → Understand → Impact Analysis
               (instalado v0.10.8; si no responde: grep/glob y registrar incidencia)
3. PLANIFICAR  superpowers:writing-plans si la fase es multi-paso
4. IMPLEMENTAR skill del dominio correspondiente (ver §5) +
               superpowers:test-driven-development
5. PROBAR      testing-unit → testing-integration → testing-e2e (skills)
6. EVIDENCIAR  cada comando relevante vía harness/scripts/evidence.sh
7. VALIDAR     python3 harness/scripts/gate_check.py --phase XX   (debe dar 0 FAIL)
8. REPORTAR    python3 harness/scripts/gen_report.py --phase XX → completar secciones
9. UAT         generar instructivo (skill uat-hitl) → EL USUARIO ejecuta y decide
10. GATE       gate-request → presentación al usuario → aprobación/rechazo
11. SOLO tras APPROVED → siguiente fase
```

**Prohibido** iniciar la fase N+1 sin gate APPROVED de la fase N (PRD §78). Analizar la siguiente sí está permitido.

---

## 4. Reglas críticas (resumen operativo del PRD §84)

1. **No instalar nada sin Dependency Proposal aprobada** (paquetes, CLIs, imágenes, MCPs, servicios). Enforcement técnico: `opencode.json`.
2. **No commit/push/merge/tag/release sin autorización explícita.** Crear ramas, editar, testear y hacer staging sí está permitido.
3. No avanzar de fase sin USER APPROVAL.
4. Nunca exponer secretos; `.env` nunca se versiona.
5. No debilitar tests ni deshabilitar validaciones para "arreglar" CI.
6. El LLM del producto no toca el Risk Engine ni habilita LIVE (restricciones del producto, respetarlas también en tests).
7. Sin data leakage: ninguna decisión usa información futura (tests lo comprueban).
8. Datasets oficiales inmutables tras congelarse (hash SHA-256).
9. Prompts/modelos no cambian silenciosamente: nueva versión + nuevo experimento.
10. PnL bruto nunca es métrica de éxito: fees + slippage + coste LLM incluidos.
11. Un backtest positivo ≠ rentabilidad demostrada.
12. Antes de declarar cualquier PASS: superpowers:verification-before-completion.

---

## 5. Routing tarea → skill

Las skills del proyecto viven en `.opencode/skills/<nombre>/SKILL.md`. Las globales se invocan por su nombre (`superpowers:...`, `python-uv`, etc.). El Skill Gap completo está en `docs/skill-gap/SKILL_GAP.md`.

| Tarea | Skill del proyecto | Globales que apoyan |
|---|---|---|
| Arquitectura / ADRs / refactor | `arquitectura-hexagonal` | code-quality, documentation-standards |
| API FastAPI | `fastapi-standards` | api-client-standards (consumo) |
| DB / migraciones / pgvector | `postgres-pgvector-alembic` | database-sql-standards |
| Contenedores | — | docker-standards |
| CI/CD GitHub Actions | `cicd-github-actions` | security-secrets |
| Secrets / credenciales | — | security-secrets |
| Observabilidad / logs | — | logging-observability |
| Config por entorno | — | configuration-environments |
| Errores / reconexiones / resiliencia | — | error-handling-resilience |
| Ingesta market data | — | data-pipeline-quality |
| Git seguro / ramas | `flujo-commits` | git-safety-guardrails |
| Dependencias / infraestructura | `infra-control` | python-uv |
| Unit tests | `testing-unit` | superpowers:test-driven-development |
| Integration tests | `testing-integration` | — |
| E2E tests | `testing-e2e` | — |
| UAT / HITL | `uat-hitl` | — |
| Evidencias | `gestion-evidencias` | — |
| Reportes de fase / PDF | `reporting-fases` | documentation-standards |
| Release readiness | `release-readiness` | — |
| Bybit (REST/WS/Testnet) | `bybit-integration` | api-client-standards |
| Backtesting / replay | `backtesting` | — |
| Risk Engine | `risk-engine` | — |
| Data leakage / no-lookahead | `data-leakage` | — |
| Walk-forward | `walk-forward-validacion` | — |
| Validación estadística | `validacion-estadistica` | — |
| LLM providers / prompts | `llm-provider-pattern` | — |
| RAG / memoria vectorial | `rag-memoria` | — |
| Memoria del codebase | `codebase-memory-mcp` | — |

---

## 6. Control de infraestructura y dependencias

Flujo obligatorio (skill `infra-control`, PRD §11):

```text
DISCOVER → PLAN/DRY-RUN → REPORT → USER GATE → APPLY → VALIDATE → EVIDENCE
```

- Pre-GATE solo comandos de lectura o dry-run (`uv add --dry-run`, `docker compose config`).
- Toda instalación usa la plantilla `harness/templates/dependency-proposal.md`.
- Instalaciones agrupadas por fase permitidas (una proposal por grupo).
- APPLY solo tras APPROVED explícito; luego VALIDATE (healthcheck/tests) y EVIDENCE.

---

## 7. Flujo Git (PRD §64–66)

**Permitido sin pedir:** crear ramas (`feature/*`, `fix/*`, `chore/*`), editar, testear, `git add` (staging), generar reportes/diffs.

**Requiere autorización explícita:** `git commit`, `git push`, `merge`, `tag`, `release`. El enforcement técnico ya los marca como `ask`.

Antes de pedir autorización de un commit, completar `harness/templates/commit-candidate.md`
(Commit Candidate Report): objetivo, rama, archivos, diff, arquitectura afectada, tests,
cobertura exacta, calidad (ruff/mypy/pytest), seguridad (sin secretos), riesgos, deuda,
y mensaje propuesto. Solo entonces presentar al usuario.

Estrategia: trunk-based simplificado; `main` protegida; commits pequeños y atómicos.

---

## 8. Testing (PRD §69–74)

| Nivel | Alcance | Gate |
|---|---|---|
| Unit | dominio puro, indicadores, risk rules, PnL, memory filtering | ≥90% cobertura global; críticos hacia 100% branch |
| Integration | FastAPI↔PostgreSQL↔pgvector, adapters↔fixtures grabados, Alembic up/down | PASS |
| E2E | flujo completo market→features→decision→risk→paper→outcome→memory→API | PASS automatizado |
| UAT | checklist HITL ejecutado por el usuario | VEREDICTO UAT: APPROVED |

- Módulos críticos (Risk Engine, portfolio accounting, sizing, kill switch, LIVE activation, mode transition, leakage guards): objetivo 100% branch.
- Cada suite se registra como evidencia con `evidence.sh` (incluye coverage.json para unit).
- Scripts del propio arnés: cobertura pragmática ~80%.

---

## 9. Progreso objetivo (única fuente: ledger)

```bash
# Ver progreso (% global/fase, pendientes, bloqueos, ETA)
python3 harness/scripts/progress.py report

# Marcar entregable completado (EXIGE ruta de evidencia)
python3 harness/scripts/progress.py mark-done --phase 03 --deliverable dataset-manifest \
  --evidence docs/phases/03/evidence/log.md

# Bloqueos
python3 harness/scripts/progress.py block --phase 04 --deliverable reconnect --motivo "..."
python3 harness/scripts/progress.py blocker-add --texto "esperando API key testnet" --phase 12
```

**Prohibido editar `harness/state/progress.yaml` a mano.** Los % se calculan sobre
entregables con evidencia; cada fase aporta máx. 90% hasta que su gate esté APPROVED;
la ETA se deriva de la velocidad observada (rango ±30%).

---

## 10. Gate de fase (PRD §77)

`gate_check.py --phase XX` valida mecánicamente: scope completo, existencia de evidencia,
coverage ≥ umbral, lint/typing registrados, UAT aprobado, aprobación humana. Produce
PASS/FAIL/MANUAL. Con 0 FAIL y MANUALs resueltos:

1. `progress.py gate-request --phase XX`
2. Entregar reporte de fase (30 secciones) + UAT al usuario
3. Usuario decide → `gate-approve` / `gate-reject`
4. Si REJECTED: registrar motivo como blocker y volver al ciclo

---

## 11. Componente educativo (Ingeniería de Software 2.0)

Cada reporte de fase documenta (sección 27): qué se desarrolló y por qué, comandos usados,
pruebas ejecutadas y competencias practicadas según PRD §80 (Git, Testing, APIs, DB,
Arquitectura, Docker, CI/CD, Security, Observability, Networking, Async, Data Eng, ML,
LLM, RAG, Agentic Systems, Experimentation, SRE, Product).

---

## 12. Referencias rápidas

```bash
uv run pytest --cov=src --cov-branch --cov-fail-under=90   # estándar producto (Fase 01+)
uv run pytest harness/tests --cov=harness/scripts \
  --cov-fail-under=80                                      # arnés
uv run ruff check . && uv run ruff format --check .        # lint/format
uv run mypy src tests                                      # typing
```

Estándares de código: ver skills `code-quality`, `python-uv` y las específicas de cada dominio.

# Self-Evaluating Trading Agent — ETH/USDT

Sistema de trading cuantitativo, observable, reproducible y auditable donde un **agente LLM** toma decisiones supervisadas sobre `ETH/USDT` (spot, long-only), las somete a un **Risk Engine determinista**, ejecuta en paper/testnet, evalúa resultados y acumula memoria experiencial — demostrando estadísticamente si aporta ventaja económica real.

> **Fuente de verdad del producto:** [`docs/PRD — Self-Evaluating Trading Agent.md`](docs/PRD%20—%20Self-Evaluating%20Trading%20Agent.md)

## Estado del proyecto

| Fase | Título | Estado |
|---|---|---|
| 00 | Governance & Agent Bootstrap (**arnés**) | done |
| 01 | Python Project Foundation | done |
| 02 | PostgreSQL & Application Skeleton | done |
| 03 | Historical Market Data | done |
| 04 | Real-Time Market Data | done |
| 05–18 | Feature Engine → Cloud Evaluation | pending |

Progreso objetivo y ETA:

```bash
python3 harness/scripts/progress.py report
```

## Cómo se desarrolla este proyecto

El desarrollo lo ejecuta un agente (OpenCode) gobernado por un arnés de gobernanza:

- **[`AGENTS.md`](AGENTS.md)** — orquestador: ciclo operativo por fase, routing a skills, reglas críticas.
- **`.opencode/skills/`** — catálogo especializado (22 skills): testing, infraestructura, dominio trading, IA.
- **`harness/`** — scripts verificadores (`progress.py`, `gate_check.py`, `evidence.sh`, reportes) + ledger objetivo.
- **`opencode.json`** — enforcement técnico: instalaciones y operaciones git destructivas requieren aprobación humana.
- **`docs/phases/`** — reportes de fase con evidencia auditable · **`docs/uat/`** — pruebas de aceptación humana.

Reglas de oro: nada se instala ni se commitea sin autorización explícita; ninguna fase avanza sin gate humano; toda afirmación PASS lleva evidencia registrada.

## Estructura

```text
AGENTS.md            # Orquestador del agente (leer primero)
opencode.json        # Permission rules de enforcement
pyproject.toml       # Config del producto (uv, ruff, mypy, pytest, coverage)
uv.lock              # Lockfile versionado
Dockerfile           # Imagen reproducible (python:3.12-slim)
.github/workflows/   # CI (quality + security + docker)
src/                 # Código del producto (layout hexagonal)
│   ├── domain/      #   entidades y reglas puras (market, trading, portfolio, risk, ...)
│   ├── application/ #   servicios y puertos
│   ├── infrastructure/  # adaptadores (bybit, database, llm, ...)
│   ├── interfaces/  #   api, web, cli
│   ├── main.py      #   entry point
│   └── version.py   #   versión única
tests/               # Suite del producto (cobertura ≥90%)
.opencode/skills/    # Catálogo de skills del proyecto
harness/
├── scripts/         # progress / gate_check / evidence / gen_report / gen_pdf / new_phase
├── state/           # progress.yaml (ledger único de avance)
├── templates/       # Plantillas: reporte, UAT, dependency-proposal, commit-candidate, ADR
└── tests/           # Suite del propio arnés (cobertura ≥80%)
docs/
├── design/          # Diseño del arnés
├── skill-gap/       # Skill Gap Report
├── phases/          # phase-XX-report.md + evidence/
├── uat/             # Instructivos UAT por fase
└── adr/             # Decisiones arquitectónicas
```

## Desarrollo del producto

Python 3.12 gestionado con `uv`. El código vive en `src/` (layout hexagonal: `domain`, `application`, `infrastructure`, `interfaces`) y los tests en `tests/`.

```bash
# 1) Entorno + dependencias
uv sync

# 2) PostgreSQL + pgvector (puerto 5433) — requiere .env con POSTGRES_PASSWORD
docker compose up -d postgres
uv run alembic upgrade head                  # migraciones

# 3) Calidad y tests (los tests de integración necesitan el postgres arriba)
uv run pytest --cov=src --cov-branch --cov-fail-under=90
uv run ruff check . && uv run ruff format --check .
uv run mypy src tests
uv run pip-audit

# 4) Ejecutar la API localmente
uv run uvicorn interfaces.api.app:app --reload
#   GET /health  GET /ready  GET /api/v1/system/state

# 5) Imagen reproducible
docker build -t self-evaluating-trading-agent:dev .
```

Configuración: `config/*.yaml` (base + modos) con defaults seguros; secretos solo en `.env` (nunca versionado). Variables de Postgres en `.env`: `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`.

CI (GitHub Actions, `.github/workflows/ci.yml`) ejecuta: `quality` (ruff + mypy), `integration` (postgres + migraciones up/down + tests/cobertura ≥90%), `security` (gitleaks + pip-audit) y `docker` (build).

## Comandos del arnés

```bash
python3 harness/scripts/progress.py report                    # progreso + ETA objetivo
python3 harness/scripts/gate_check.py --phase XX              # checklist DoD de fase
bash harness/scripts/evidence.sh <fase> <nombre> -- <cmd...>  # evidencia auditable
uv run --project harness pytest harness/tests                 # tests del arnés
```

## Licencia y advertencia

Proyecto educativo local. El trading LIVE permanece deshabilitado por defecto (PRD §49–50); la rentabilidad es una hipótesis no demostrada hasta superar los gates estadísticos del PRD §47.

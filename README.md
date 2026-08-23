# Self-Evaluating Trading Agent — ETH/USDT

Sistema de trading cuantitativo, observable, reproducible y auditable donde un **agente LLM** toma decisiones supervisadas sobre `ETH/USDT` (spot, long-only), las somete a un **Risk Engine determinista**, ejecuta en paper/testnet, evalúa resultados y acumula memoria experiencial — demostrando estadísticamente si aporta ventaja económica real.

> **Fuente de verdad del producto:** [`docs/PRD — Self-Evaluating Trading Agent.md`](docs/PRD%20—%20Self-Evaluating%20Trading%20Agent.md)

## Estado del proyecto

| Fase | Título | Estado |
|---|---|---|
| 00 | Governance & Agent Bootstrap (**arnés**) | done |
| 01 | Python Project Foundation | done |
| 02–18 | PostgreSQL Skeleton → Cloud Evaluation | pending |

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
uv sync                                                    # instalar dependencias + entorno (.venv)
uv run pytest --cov=src --cov-branch --cov-fail-under=90   # tests + cobertura ≥90%
uv run ruff check .                                        # lint
uv run ruff format --check .                               # formato
uv run mypy src tests                                      # typing (strict)
uv run pre-commit install                                  # hooks git (una vez)
uv run pip-audit                                           # auditoría de CVEs
docker build -t self-evaluating-trading-agent:dev .        # imagen reproducible
docker run --rm self-evaluating-trading-agent:dev          # ejecutar el entry point
```

CI (GitHub Actions, `.github/workflows/ci.yml`) ejecuta la misma secuencia (`uv sync --frozen` + lint + typing + tests/coverage + secret scanning + dependency audit + build de imagen) y queda activa desde el primer push autorizado a `main`.

## Comandos del arnés

```bash
python3 harness/scripts/progress.py report                    # progreso + ETA objetivo
python3 harness/scripts/gate_check.py --phase XX              # checklist DoD de fase
bash harness/scripts/evidence.sh <fase> <nombre> -- <cmd...>  # evidencia auditable
uv run --project harness pytest harness/tests                 # tests del arnés
```

## Licencia y advertencia

Proyecto educativo local. El trading LIVE permanece deshabilitado por defecto (PRD §49–50); la rentabilidad es una hipótesis no demostrada hasta superar los gates estadísticos del PRD §47.

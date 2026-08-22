# Self-Evaluating Trading Agent — ETH/USDT

Sistema de trading cuantitativo, observable, reproducible y auditable donde un **agente LLM** toma decisiones supervisadas sobre `ETH/USDT` (spot, long-only), las somete a un **Risk Engine determinista**, ejecuta en paper/testnet, evalúa resultados y acumula memoria experiencial — demostrando estadísticamente si aporta ventaja económica real.

> **Fuente de verdad del producto:** [`docs/PRD — Self-Evaluating Trading Agent.md`](docs/PRD%20—%20Self-Evaluating%20Trading%20Agent.md)

## Estado del proyecto

| Fase | Título | Estado |
|---|---|---|
| 00 | Governance & Agent Bootstrap (**arnés**) | in_progress |
| 01–18 | Python Foundation → Cloud Evaluation | pending |

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

## Comandos del arnés

```bash
python3 harness/scripts/progress.py report                    # progreso + ETA objetivo
python3 harness/scripts/gate_check.py --phase XX              # checklist DoD de fase
bash harness/scripts/evidence.sh <fase> <nombre> -- <cmd...>  # evidencia auditable
uv run --project harness pytest harness/tests                 # tests del arnés
```

## Licencia y advertencia

Proyecto educativo local. El trading LIVE permanece deshabilitado por defecto (PRD §49–50); la rentabilidad es una hipótesis no demostrada hasta superar los gates estadísticos del PRD §47.

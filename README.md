# Self-Evaluating Trading Agent

Sistema de trading cuantitativo donde un **agente LLM** toma decisiones supervisadas sobre mercados crypto (spot, long-only), las somete a un **Risk Engine determinista**, ejecuta en paper/testnet, evalúa resultados y acumula memoria experiencial — demostrando estadísticamente si aporta ventaja económica real.

> **Fuente de verdad del producto:** [`docs/PRD.md`](docs/PRD.md)
> **Rama canónica:** `main` (única fuente de verdad del código)

## Estado del proyecto

| Fase | Estado | Notas |
|---|---|---|
| 00–05 | **done** | Foundations, DB, Market Data |
| 06–15 | **done** | Backtesting, ML, LLM, Risk, Paper, Eval, Dashboard |
| 16 | **ACTIVE** | Paper Trading Certification en curso (lenovosrv) |
| 18 | **done** | LLM Development Evaluation |
| 21R | **CLOSED** | Runtime Integrity Recovery — evidencia consolidada |

### Resultados Fase 21R (Autoritativos)

| Estrategia | Trades | Gross Ref PnL | Net PnL | Viabilidad Absoluta |
|---|---|---|---|---|
| Baseline (EMA/RSI) | 634 | +$4.96 | -$25.48 | **FAIL** |
| Donchian Breakout | 1,086 | +$6.86 | -$45.27 | **FAIL** |
| Bollinger Mean Reversion | 460 | +$1.65 | -$20.43 | **FAIL** |

**Posicionamiento:** CAPPED_ALLOCATION_NOTIONAL (budget ATR, capped a $20 notional). NO es 2% capital-at-risk.

**Walk-Forward:** NO autorizado (todas las estrategias FAIL en viabilidad absoluta).

**Holdout:** PRISTINE (0 reads, 0 ejecuciones).

**Certificación Paper:** ACTIVA en lenovosrv. Phase 21R = CLOSED. Certification restart required = NO.

**Siguiente trabajo:** Phase 22 — Execution Economics (costos reales de ejecución).

## Arquitectura

```text
src/                     # Código del producto (layout hexagonal)
├── domain/              #   entidades y reglas puras
│   ├── market/          #     velas, timeframes, instrumentos
│   ├── trading/         #     señales, decisiones, órdenes
│   ├── portfolio/       #     posición, cash, PnL
│   └── risk/            #     sizing, stops, kill switch, drawdown
├── application/         #   servicios y puertos
│   └── services/        #     paper_engine, decision_engine, backtest_runner
├── infrastructure/      #   adaptadores (bybit, postgres, llm, embeddings)
├── interfaces/          #   api, web, cli
├── lab/                 #   session_runner, strategy_lab
└── main.py              #   entry point
```

### Componentes principales

| Componente | Ubicación | Función |
|---|---|---|
| **PaperEngine** | `src/application/services/paper_engine.py` | Ejecución paper con fills, fees, PnL, exit_reason |
| **RiskEngine** | `src/domain/risk/engine.py` | Determinista: sizing → stops → limits → kill_switch |
| **DecisionEngine** | `src/application/services/decision_context.py` | Agrega features, contexto, llama LLM |
| **Strategy Lab** | `src/lab/` | Evaluación de estrategias históricas |
| **Trading Memory** | `src/infrastructure/memory/` | pgvector embeddings, RAG, reflexiones |

### Mercado y ejecución

- **Exchange:** Bybit (spot, REST + WebSocket)
- **Par:** ETH/USDT
- **Modo:** Long-only
- **LIVE:** Deshabilitado permanentemente (PRD §49–50)

## Desarrollo

Python 3.12 gestionado con `uv`. PostgreSQL + pgvector para memoria.

```bash
# Entorno + dependencias
uv sync

# PostgreSQL (puerto 5433)
docker compose up -d postgres
uv run alembic upgrade head

# Tests y calidad
uv run pytest --cov=src --cov-branch --cov-fail-under=90
uv run ruff check . && uv run ruff format --check .
uv run mypy src tests

# API local
uv run uvicorn src.interfaces.api.app:app --reload
```

## Estructura del repositorio

```text
main                  # Rama canónica (source of truth)
AGENTS.md             # Orquestador del agente (leer primero)
opencode.json         # Permission rules de enforcement
pyproject.toml        # Config del producto
src/                  # Código del producto
tests/                # Suite del producto (≥90% coverage)
harness/              # Scripts verificadores + ledger
├── scripts/          #   progress, gate_check, evidence, gen_report
├── state/            #   progress.yaml (ledger de avance)
└── templates/        #   plantillas de reportes
docs/
├── PRD.md            #   Product Requirements Document
├── phases/           #   reportes de fase + evidence/
│   └── 21R/          #   Phase 21R closure + authoritative evidence
├── design/           #   diseño del arnés
└── adr/              #   decisiones arquitectónicas
```

## Comandos del arnés

```bash
python3 harness/scripts/progress.py report                    # progreso + ETA
python3 harness/scripts/gate_check.py --phase XX              # checklist DoD
bash harness/scripts/evidence.sh <fase> <nombre> -- <cmd...>  # evidencia auditable
uv run --project harness pytest harness/tests                 # tests del arnés
```

## Licencia y advertencia

Proyecto educativo local. El trading LIVE permanece deshabilitado por defecto (PRD §49–50); la rentabilidad es una hipótesis no demostrada hasta superar los gates estadísticos del PRD §47.

# Commit Candidate Report — 2026-09-06 (Fase 16b: max_daily_loss + slippage)

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

Corregir dos bugs de risk accounting detectados en la auditoría del replay de 36 meses (sin tocar estrategia, thresholds, sizing, fee model ni slippage rate):

1. **Bug #1 — `max_daily_loss` sin reset diario:** `PaperEngine._realized_pnl_today` acumulaba PnL de toda la sesión; un único cruce bajo −$20 (2% de $1,000) bloqueaba el trading ~683 días continuos. Fix: reset diario UTC (`utc_day_index`), guard solo sobre BUY (SELL/stop/TP/trailing/cierres siguen permitidos), métricas separadas, rechazo explícito de timestamps fuera de orden.
2. **Bug #2 — slippage doble contabilizada:** slippage embebida en `exec_price` y además re-restada en `net_pnl`. Fix (Opción A): `net_pnl = gross − fees`; slippage queda como métrica analítica. Resultado: reconciliación contable con residual 0.

## Rama

| Campo | Valor |
|---|---|
| branch | `fix/phase-16b-paper-runner-atr` |
| base commit | `b47ff28` (fix ATR + ws.close + invalidación, ya desplegado) |

## Archivos

- **Creados:** `src/domain/time/day.py` (`utc_day_index`), `tests/test_daily_loss_reset.py` (reset/guard/out-of-order/paridad), `tests/test_pnl_reconciliation.py` (round-trip + residual).
- **Modificados:** `src/application/services/paper_engine.py`, `src/domain/risk/engine.py`, `src/domain/portfolio/portfolio.py`, `src/domain/evaluation/metrics.py`, `src/version.py` (0.1.0→0.1.1), `tests/test_risk_engine.py`, `tests/test_metrics.py`, `tests/test_portfolio.py`.
- **Eliminados:** —

## Diff

```bash
9 files changed, 117 insertions(+), 21 deletions(-)   # + 3 archivos nuevos (day.py + 2 tests)
```

## Arquitectura afectada (blast radius vía codebase-memory-mcp `trace_path`)

| Símbolo modificado | Consumidores inbound |
|---|---|
| `RiskEngine.evaluate` | solo `PaperEngine.on_price` (+ `PaperRunner.handle_kline`, `paper_session` transitivos) |
| `PaperEngine.on_price` | `PaperRunner.handle_kline`, `cli.paper_runner._run/_run_loop`, `paper_session.run_paper_session`, `main.main` |
| `Portfolio.apply_sell` (net_pnl) | `PaperEngine._check_exits/_close_position/on_price`, `ml_pipeline.run_ml_baseline`, `buy_hold.run_buy_and_hold`, `backtest.run_backtest`, `paper_session.run_paper_session` |
| `compute_metrics` (net_pnl) | `paper_session`, `backtest`, `buy_hold`, `ml_pipeline` |

El bug #2 propaga a **backtest, ml_pipeline, buy_hold, paper_session, paper_runner** (todos consumen `realized/net PnL`); el bug #1 afecta **paper_runner + paper_session** (replay+paper), no al backtest (motor propio).

**`detect_changes` (ejecutado pre-commit):** base `main` → `HEAD` (`b47ff28`): `changed_files=410`, `impacted_total=127` símbolos, `seed_symbols=2833`; módulos impactados: `src/interfaces 12`, `src/application 6`, `src/domain 5`, `src/infrastructure 5`, `harness/scripts 2`, `harness/tests 4`, `migrations 1`, etc. Nota: `detect_changes` opera sobre diffs **commiteados** (`<ref>...HEAD`); como el WIP aún no está commiteado, este resultado refleja el alcance de la rama `fix/phase-16b` frente a `main`, no el delta sin commitear. El blast radius **preciso del WIP** es el de `trace_path` (tabla superior). Se re-ejecutará `detect_changes` + re-index **inmediatamente tras el commit** (regla §4.13) para reflejar el diff real.

## Índice del grafo

- [x] Re-indexado (`index_repository`, proyecto `seta-phase-16b-fix`, 7,946 nodos / 20,717 aristas)
- [x] `check_index_coverage` limpio sobre los 12 archivos tocados
- [ ] `detect_changes` + re-index final tras el commit (regla §4.13)

## Tests ejecutados

| Suite | Resultado |
|---|---|
| Unit (`tests/`, sin integration) | PASS |
| Integration (`tests/integration/`, PostgreSQL 5433) | **PASS (16)** |
| E2E (`tests/e2e/test_e2e_fixes.py`: E2E-1 + E2E-2) | **PASS (2)** |
| Suite completa `tests/` (unit + integration + e2e) | **491 passed, 1 skipped** |
| `test_daily_loss_reset.py` (13) | PASS |
| `test_pnl_reconciliation.py` (9) | PASS |
| `test_risk_engine.py` / `test_metrics.py` / `test_portfolio.py` (actualizados) | PASS |

**Test skipped (justificado):** `tests/test_fastembed_provider.py:97` — smoke del modelo de embeddings real que exige `RUN_MODEL_SMOKE=1` (descarga/ejecuta el modelo local, opt-in por coste/tiempo). No guarda relación con los fixes de risk accounting; **no es cobertura pendiente** de este cambio.

## Cobertura

`--cov=src --cov-branch` (unit + integration): **TOTAL 94.62% · branch 95%** (umbral 90% superado).

Branch de componentes críticos: `risk/engine.py` 100% · `risk/guards.py` 100% · `portfolio.py` 100% · `metrics.py` 100% · `time/day.py` 100% · `paper_engine.py` 98%.

## Calidad

```bash
ruff check .            # All checks passed!
ruff format --check .   # 235 files already formatted
mypy src tests          # Success: no issues found in 207 source files
```

## Seguridad

- [x] Sin secretos en el diff (scan `api_key|secret|password|token|BEGIN PRIVATE|...` limpio)
- [x] Sin `.env` ni credenciales

## Replay 36 meses (reproducible)

- Dataset: `BYBIT_ETHBTC_V001` · ETHUSDT 15m · 2023-09-08 → 2026-08-23 · 103,680 velas.
- **Determinista:** dos corridas byte-idénticas (diff vacío).
- **Reconciliación:** `reconciliation_residual = 0.0` (evidencia `docs/phases/16b/evidence/reconciliation-AFTER.json`).

### Benchmark oficial corregido de `baseline-v1`

| Métrica | Valor |
|---|---|
| BUY signals | 1,055 |
| Trades cerrados | 1,055 |
| Net PnL | −$43.26 |
| Final equity | $956.74 |
| Profit Factor | 0.680 |
| Expectancy | −$0.0410 |
| Max Drawdown | 4.38% |

> **`baseline-v1` no demuestra edge económico y no es candidata a LIVE** (expectativa negativa; el PnL neto tras fees+slippage es negativo).

## Riesgos residuales

1. `interfaces/cli/paper_runner.py` (77%) y `paper_runner.py` service (86%) mantienen gaps de cobertura preexistentes en rutas live DB/WS (se cubren en integration/E2E con DB); no tocadas por este fix.
2. Los contadores (`orders_rejected`, `daily_loss_triggered`, `daily_loss_active_cycles`) están en el motor pero aún no se exponen en el reporte periódico/dashboard (observabilidad diferida).
3. `max_daily_loss` correcto nunca dispara con `baseline-v1` (pérdidas diarias < $20); el guard queda como protección latente.

## Deuda técnica

- Evidencia duplicada entre el worktree de la rama fix y la raíz `feature/phase-08-llm-decision-agent` hasta integrar ramas.
- `test_gen_pdf.py` requiere dev-deps `markdown`/`weasyprint` (Dependency Proposal pendiente); falla por entorno, no por regresión.
- `opencode.json` con MCP `chrome-devtools` sin commitear (requiere Dependency Proposal).

## Rollback

- `git revert <commit>` revierte ambos fixes (dominio puro + tests); no hay migraciones ni cambios de schema.
- La versión desplegada en `lenovosrv` (commit `b47ff28`) sigue operativa; este commit no redeploya.

## Mensaje de commit propuesto

```
fix(phase-16b): reset diario UTC de max_daily_loss + eliminar doble conteo de slippage

- PaperEngine: reset _realized_pnl_today en cada frontera de día UTC (utc_day_index
  puro, sin datetime.now()); rechazo explícito de timestamps fuera de orden sin mutar
  estado; métricas separadas orders_rejected / daily_loss_triggered /
  daily_loss_active_cycles
- RiskEngine: guard max_daily_loss aplicado solo a BUY (nueva exposición); SELL y
  cierres reductores de riesgo (stop/TP/trailing/forzoso) siempre permitidos; HOLD
  deja de registrarse como orden rechazada
- Portfolio + compute_metrics: net_pnl = gross - fees (slippage ya embebida en
  exec_price; se conserva como métrica analítica) -> reconciliación residual 0
- version 0.1.0 -> 0.1.1 (ambos bugfixes; strategy_version=baseline-v1 y risk-v1 sin
  cambios)
- tests: test_daily_loss_reset.py + test_pnl_reconciliation.py + actualización de
  test_risk_engine/test_metrics/test_portfolio
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

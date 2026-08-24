# Phase 06 — Backtesting & Deterministic Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir un motor de backtesting event-driven determinista (dominio puro) con una estrategia baseline de reglas versionada, contabilidad de portfolio exacta, modelos de fees/slippage/fills y métricas completas (PRD §45), más el benchmark Buy & Hold.

**Architecture:** Todo puro y determinista en `src/domain/{trading,portfolio,evaluation}`; el motor orquesta en `src/application/services/backtest_engine.py`. Regla de no-lookahead: la señal generada al cierre de la vela `i` se ejecuta al **open de la vela `i+1`**. Sin I/O, sin dependencias nuevas. `float` IEEE-754 determinista (continuación de ADR-0002).

**Tech Stack:** Python 3.12 stdlib (`math`, `statistics`, `dataclasses`, `StrEnum`, `collections.deque`). Sin dependencias nuevas.

## Global Constraints

- Sin dependencias nuevas. Dominio puro (cero I/O, cero frameworks).
- Determinismo: sin aleatoriedad; iteración ordenada por `timestamp_ms`.
- No-lookahead (PRD §34): señal en cierre de `i` → ejecución en open de `i+1`.
- Costos siempre: fees reales Bybit parametrizados + slippage conservador (PRD §27–28). Nunca PnL bruto como métrica única.
- Portfolio exacto: SELL solo reduce posición existente (long-only spot, sin short); cash nunca negativo.
- Estilo: `from __future__ import annotations`, `dataclass(frozen=True, slots=True)`, `StrEnum`.
- Lint/typing: `ruff check .`, `ruff format --check .`, `mypy src tests` (strict).
- Cobertura: `uv run pytest --cov=src --cov-branch --cov-fail-under=90`; módulos de PnL/portfolio/fills/slippage/fees hacia 100% branch.

---

### Task 1: Señal, fees, slippage y fill

**Files:**
- Create: `src/domain/trading/signal.py`
- Create: `src/domain/trading/fees.py`
- Create: `src/domain/trading/slippage.py`
- Create: `src/domain/trading/fill.py`
- Test: `tests/test_costs_fill.py`

**Interfaces:**
- Produces:
  - `Action(StrEnum)`: `BUY`, `SELL`, `HOLD`.
  - `Intensity(StrEnum)`: `LOW`, `MEDIUM`, `HIGH`.
  - `Signal(timestamp_ms: int, action: Action, intensity: Intensity = MEDIUM, reason: str = "")`.
  - `FeeModel(taker_bps: float = 10.0, version: str = "bybit-spot-v1")` con `fee(notional: float) -> float` (notional * bps / 10_000).
  - `SlippageModel(bps: float = 2.0, version: str = "conservative-v1")` con `cost(notional: float) -> float`.
  - `Fill(timestamp_ms, action, price, exec_price, quantity, notional, fee, slippage_cost)`.
  - `FillModel(fee_model, slippage_model)`: `buy(timestamp_ms, price, cash) -> Fill` y `sell(timestamp_ms, price, quantity) -> Fill`.

**Semántica de `FillModel`:**
- `buy(price, cash)`: `exec_price = price * (1 + slippage_bps/10000)`; `max_notional = cash / (1 + fee_rate)`; `quantity = max_notional / exec_price`; `fee = notional * fee_rate`; `notional = quantity * exec_price`. Gasta todo el cash disponible (fee incluida).
- `sell(price, quantity)`: `exec_price = price * (1 - slippage_bps/10000)`; `notional = quantity * exec_price`; `fee = notional * fee_rate`; `slippage_cost = quantity * (price - exec_price)`.
- `buy` con `cash <= 0` ⇒ `quantity=0` (sin fill). `sell` con `quantity <= 0` ⇒ `quantity=0`.

- [ ] **Step 1: tests** — `tests/test_costs_fill.py` (fees/slippage redondeos, buy gasta cash+fee, sell aplica slippage, casos cero).

- [ ] **Step 2:** verificar FAIL.
- [ ] **Step 3:** implementar.
- [ ] **Step 4:** verificar PASS.
- [ ] **Step 5:** commit al final de la fase.

---

### Task 2: Portfolio accounting

**Files:**
- Create: `src/domain/portfolio/portfolio.py`
- Test: `tests/test_portfolio.py`

**Interfaces:**
- `Trade(entry_ts, exit_ts, entry_price, exit_price, quantity, gross_pnl, fees, slippage, net_pnl)` (frozen).
- `Portfolio(initial_cash: float)`:
  - campos: `cash`, `position: float`, `avg_entry: float | None`, `realized_pnl`, `total_fees`, `total_slippage`, `trades: list[Trade]`.
  - `apply_buy(fill) -> None`: `cash -= notional + fee`; `position += quantity`; actualiza `avg_entry` (media ponderada).
  - `apply_sell(fill) -> None`: reduce posición; registra `Trade` si cierra del todo (o parcial); `cash += notional - fee`; `realized_pnl += ...`.
  - `equity(price) -> float`: `cash + position * price`.
  - `open_value(price) -> float`: `position * price`.

**Invariantes (test):** SELL nunca deja posición negativa (lanza `ValueError` o ignora exceso); cash nunca negativo; `apply_buy` no gasta más que `cash`.

- [ ] **Step 1:** tests (compra con fee, venta reduce posición y registra trade, sin short, sin cash negativo, equity).
- [ ] **Step 2–5:** RED→GREEN, commit fase.

---

### Task 3: Métricas (PRD §45)

**Files:**
- Create: `src/domain/evaluation/metrics.py`
- Test: `tests/test_metrics.py`

**Interfaces:**
- `PerformanceMetrics` (frozen) con: `gross_pnl, net_pnl, fully_loaded_pnl, fees, slippage, llm_cost, trades, win_rate, loss_rate, profit_factor, sharpe, sortino, max_drawdown, expectancy, avg_winner, avg_loser, risk_reward, avg_holding_bars, exposure`.
- `compute_metrics(trades, equity_curve, periods_per_year, llm_cost=0.0) -> PerformanceMetrics`.
  - `equity_curve: Sequence[float]` (mark-to-market por vela).
  - `gross_pnl = sum(t.gross_pnl)`; `fees = sum(t.fees)`; `slippage = sum(t.slippage)`; `net_pnl = gross_pnl - fees - slippage`; `fully_loaded_pnl = net_pnl - llm_cost`.
  - `win_rate = wins/trades` (net_pnl > 0). `profit_factor = gross_profit / gross_loss` (0 si no hay pérdidas: `inf` si hay ganancias).
  - `sharpe = mean(ret)/std(ret) * sqrt(periods_per_year)`; `sortino` con downside deviation (solo retornos negativos).
  - `max_drawdown` en % desde pico de equity.
  - `expectancy = mean(net_pnl por trade)`. `avg_winner`/`avg_loser`. `risk_reward = avg_winner/|avg_loser|`.
  - `exposure = fracción de velas con posición abierta`.

- [ ] **Step 1:** tests (casos: sin trades, solo ganadoras, solo perdedoras, drawdown conocido, sharpe de serie constante=0).
- [ ] **Step 2–5.**

---

### Task 4: Baseline determinista versionada

**Files:**
- Create: `src/domain/trading/strategy.py`
- Test: `tests/test_strategy.py`

**Interfaces:**
- `Strategy(Protocol)`: `version: str`; `on_candle(candle: Candle) -> Signal`.
- `EmaRsiBaseline` (versión `"baseline-v1"`):
  - `EmaRsiConfig(ema_fast=20, ema_slow=50, rsi_period=14, rsi_exit=80, rsi_entry_ceiling=70)`.
  - Trackers incrementales (`_EmaTracker`, `_RsiTracker`) con seeds idénticos a `domain.market.indicators.ema`/`rsi` (SMA/Wilder).
  - Reglas: **BUY** si cruce EMA-fast↑ sobre EMA-slow (prev≤ y now>) y RSI < `rsi_entry_ceiling`; **SELL** si cruce EMA-fast↓ bajo EMA-slow (prev≥ y now<) o RSI > `rsi_exit`; si no, **HOLD**.

- [ ] **Step 1:** tests: (a) equivalencia incremental vs `indicators.ema`/`rsi`; (b) BUY en cruce alcista; (c) SELL en cruce bajista; (d) SELL por RSI overbought; (e) HOLD sin señal; (f) no señal antes del warmup.
- [ ] **Step 2–5.**

---

### Task 5: Motor backtest event-driven + no-lookahead

**Files:**
- Create: `src/application/services/backtest_engine.py`
- Test: `tests/test_backtest_engine.py`, `tests/test_backtest_no_lookahead.py`

**Interfaces:**
- `BacktestEngine(strategy, fill_model)`:
  - `run(candles: Sequence[Candle]) -> BacktestResult`.
  - `BacktestResult` (frozen): `portfolio`, `trades`, `equity_curve`, `metrics`, `signals: int`.
- Algoritmo (determinista, causal):
  1. Por cada vela `i` (orden por timestamp):
     a. Si hay señal pendiente de `i-1`, ejecutar en `open` de `i` (BUY/SELL vía `FillModel`).
     b. `signal = strategy.on_candle(candles[i])`; quedarla pendiente.
     c. Registrar `equity(candles[i].close)`.
  2. Al final, `compute_metrics(trades, equity_curve, periods_per_year)`.

- [ ] **Step 1:** tests de engine (happy path buy→sell produce PnL y trade; determinismo: dos corridas idénticas; sin señal pendiente al final no se ejecuta).
- [ ] **Step 2:** `test_backtest_no_lookahead.py`: envenenar velas futuras y verificar que las decisiones/trades hasta `t` no cambian; replay truncado idéntico.
- [ ] **Step 3–5.**

---

### Task 6: Benchmark Buy & Hold

**Files:**
- Create: `src/domain/evaluation/buy_hold.py`
- Test: `tests/test_buy_hold.py`

**Interfaces:**
- `run_buy_and_hold(candles, fill_model, periods_per_year) -> PerformanceMetrics`:
  - Compra con todo el cash al `open` de la primera vela; mantiene; vende al `close` de la última. Reutiliza `FillModel`/`Portfolio`/`compute_metrics` para métricas comparables.

- [ ] **Step 1–5.**

---

### Task 7: ADR-0003, evidencia, gate y reporte

- ADR-0003 (motor determinista float + no-lookahead por open de vela siguiente).
- Evidencia: unit-tests + coverage.json + lint + format + typing vía `evidence.sh`.
- Marcar 8 entregables done; `gate_check.py --phase 06` ⇒ 0 FAIL; reporte (30 secciones) + UAT.

## Self-Review

- **Spec coverage:** §25 (simulador determinista: fills/fees/slippage/balances/PnL) → Tasks 1–2; §27 fees → Task 1; §28 slippage → Task 1; §29 baseline determinista → Task 4; §45 métricas → Task 3; §31 Buy & Hold → Task 6; no-lookahead §34 → Task 5. ✓
- **Placeholders:** fórmulas y firmas completas. ✓
- **Type consistency:** `Signal`, `Fill`, `Portfolio`, `Trade`, `PerformanceMetrics`, `BacktestResult` consistentes entre tasks. ✓

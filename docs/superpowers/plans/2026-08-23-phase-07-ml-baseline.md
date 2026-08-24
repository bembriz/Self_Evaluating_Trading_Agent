# Phase 07 — ML Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir un baseline ML reproducible (Logistic Regression) en Python puro, evaluado con walk-forward sin shuffle y con métricas comparables al baseline determinista y Buy & Hold.

**Architecture:** Regresión logística implementada en stdlib (ADR-0004, continuación de ADR-0002: sin numpy/sklearn). Pipeline puro: `build_features` (causal) → `WalkForwardSplitter` (cronológico) → entrenar/predecir → señales → `BacktestEngine` (reusado de Fase 06) → `PerformanceMetrics` comparables. `ExperimentMetadata` con `experiment_id` inmutable (hash) por PRD §39.

**Tech Stack:** Python 3.12 stdlib (`math`, `statistics`, `hashlib`, `dataclasses`). **Sin dependencias nuevas.**

## Global Constraints

- Sin dependencias nuevas (sin numpy/sklearn): regresión logística stdlib puro (ADR-0004).
- No-lookahead (PRD §34): la feature en `t` usa solo datos ≤ `t`; la etiqueta `y[t]` usa `close[t+1]` (permitido: es el objetivo, no una feature).
- Walk-forward (PRD §43): sin shuffle temporal; train estrictamente anterior a validation; holdout excluido.
- Determinismo: regresión logística con pesos inicializados a cero y gradient descent determinista (sin aleatoriedad no sembrada).
- Cobertura ≥90%; `ruff check .`/`ruff format --check .`/`mypy src tests` verdes.

---

### Task 1: Regresión logística pura

**Files:**
- Create: `src/domain/experiments/logistic_regression.py`
- Test: `tests/test_logistic_regression.py`

**Interfaces:**
- `LogisticRegression(learning_rate=0.1, max_iter=1000, l2=0.0, tol=1e-6)`:
  - `fit(X: Sequence[Sequence[float]], y: Sequence[int]) -> None`
  - `predict_proba(X) -> list[float]` (P(y=1))
  - `predict(X, threshold=0.5) -> list[int]`
  - `weights: list[float]`, `bias: float`
- Gradient descent batch, `w` inicializado a ceros, sigmoid con clip en `[-30, 30]` para estabilidad numérica. Pérdida = log-loss + l2*||w||².

- [ ] **Step 1:** tests: (a) conjunto linealmente separable → accuracy 1.0; (b) predict_proba en [0,1]; (c) determinismo (dos fits idénticos); (d) l2 reduce ||w||; (e) predict respeta threshold.
- [ ] **Step 2–5:** RED→GREEN, commit fase.

---

### Task 2: Feature builder causal + etiquetas

**Files:**
- Create: `src/domain/experiments/features.py`
- Test: `tests/test_ml_features.py`

**Interfaces:**
- `FeatureMatrix(indices: list[int], features: list[list[float]], labels: list[int])`.
- `build_features(candles: Sequence[Candle]) -> FeatureMatrix`:
  - features en `t` = `[return_t, rsi_norm, momentum, volatility]` (reutiliza `indicators`):
    - `return_t = (close[t]-close[t-1])/close[t-1]`
    - `rsi_norm = rsi[t]/50 - 1`
    - `momentum` (10-bar), `realized_volatility` (20-bar).
  - `labels[t] = 1 si close[t+1] > close[t] else 0`.
  - Solo incluye barras `t` con todas las features no-None y `t+1` existente.

- [ ] **Step 1:** tests: (a) features en t no cambian si enveneno candles futuras; (b) label es signo del retorno siguiente; (c) barras warmup excluidas; (d) longitud alineada (indices/features/labels).
- [ ] **Step 2–5.**

---

### Task 3: Walk-forward splitter

**Files:**
- Create: `src/domain/experiments/walk_forward.py`
- Test: `tests/test_walk_forward.py`

**Interfaces:**
- `WalkForwardConfig(initial_train: int, val_size: int, step: int, holdout_size: int = 0)`.
- `WalkForwardSplitter(config)`:
  - `windows(n: int) -> list[tuple[int, int, int]]` (train_end, val_start, val_end) cronológicos: train `[0, t)`, val `[t, t+val_size)`, `t` desde `initial_train` incrementando `step`; `val_end <= n - holdout_size` (holdout nunca se toca).
- Reglas duras: sin shuffle, sin solapamiento train/val, train siempre < val.

- [ ] **Step 1:** tests: (a) ventanas cronológicas y contiguas; (b) holdout excluido; (c) n pequeño → sin ventanas; (d) train < val siempre.
- [ ] **Step 2–5.**

---

### Task 4: Experiment tracking (experiment_id inmutable)

**Files:**
- Create: `src/domain/experiments/experiment.py`
- Test: `tests/test_experiment.py`

**Interfaces:**
- `ExperimentMetadata` (frozen) con los campos mínimos PRD §39 (`experiment_id`, `git_commit`, `dataset_version`, `strategy_version`, `feature_config_version`, `fees_model_version`, `slippage_model_version`, `random_seed`, `started_at`, `finished_at`, y `params: dict[str, str]`).
- `build_experiment_id(metadata) -> str`: `sha256` de la serialización canónica de los campos (sin `experiment_id`, sin timestamps) → hex truncado (p. ej. 16 chars).
- El `experiment_id` es inmutable (se calcula de los parámetros; cambiar un parámetro cambia el id).

- [ ] **Step 1:** tests: (a) mismos params → mismo id; (b) cambiar un param → id distinto; (c) id estable ante reordenación de dict; (d) length/sin caracteres raros.
- [ ] **Step 2–5.**

---

### Task 5: Pipeline ML + métricas comparables

**Files:**
- Create: `src/domain/trading/strategy.py` (añadir `PrecomputedStrategy`)
- Create: `src/application/services/ml_pipeline.py`
- Test: `tests/test_ml_pipeline.py`

**Interfaces:**
- `PrecomputedStrategy(actions: Sequence[Action])` (en `strategy.py`): `on_candle(candle)` devuelve `Signal(timestamp_ms, actions[i])` con contador interno. Reutilizable para backtest de señales precalculadas.
- `MlBaselineConfig(walk_forward: WalkForwardConfig, logistic: LogisticRegression-like, buy_threshold=0.55, sell_threshold=0.45, ...)`.
- `run_ml_baseline(candles, config) -> MlBaselineResult`:
  - `features = build_features(candles)`.
  - Por cada ventana WF: `LogisticRegression.fit(train)`, `predict_proba(val)`.
  - Predicciones por barra → acciones (`> buy_threshold` BUY, `< sell_threshold` SELL, else HOLD; barras sin predicción → HOLD).
  - Backtest con `BacktestEngine(PrecomputedStrategy(actions))` → `PerformanceMetrics`.
  - `classification_metrics = {accuracy, precision, recall, n}` sobre las barras de validation.
- `MlBaselineResult` (frozen): `metrics: PerformanceMetrics`, `classification: dict[str, float]`, `experiment_id: str`.

- [ ] **Step 1:** tests: (a) pipeline corre sin error y produce métricas; (b) señales ML alimentan el engine (trades generados); (c) determinismo (dos corridas idénticas); (d) métricas de clasificación correctas sobre un conjunto conocido.
- [ ] **Step 2–5.**

---

### Task 6: Tests anti-lookahead ML

**Files:**
- Create: `tests/test_ml_no_lookahead.py`

- [ ] **Step 1:** tests: (a) `build_features` invariante al envenenar futuro (features/indices/labels idénticos); (b) walk-forward train < val (ninguna ventana usa futuro); (c) `PrecomputedStrategy`/engine: envenenar velas futuras no cambia equity/trades antes del punto.
- [ ] **Step 2–5.**

---

### Task 7: ADR-0004, evidencia, gate y reporte

- ADR-0004 (regresión logística stdlib puro, sin sklearn/numpy).
- Evidencia vía `evidence.sh` + `coverage.json`.
- Marcar 6 entregables done; `gate_check.py --phase 07` ⇒ 0 FAIL; reporte + UAT.

## Self-Review

- **Spec coverage:** §30 logistic regression reproducible → Task 1; pipeline reproducible → Task 2+5; §43 walk-forward sin shuffle → Task 3; §39 experiment_id → Task 4; métricas comparables → Task 5 (reusa BacktestEngine/PerformanceMetrics); §34 leakage → Task 6. ✓
- **Placeholders:** fórmulas/firmas completas. ✓
- **Type consistency:** `FeatureMatrix`, `WalkForwardSplitter.windows`, `LogisticRegression`, `ExperimentMetadata`, `MlBaselineResult`, `PrecomputedStrategy` consistentes entre tasks. ✓

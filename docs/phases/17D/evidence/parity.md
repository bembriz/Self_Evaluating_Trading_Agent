# FASE 17D — Mode 2 Runtime Parity (Strategy Lab)

> Sin segundo motor: Strategy real + RiskEngine real (vía PaperEngine real).
> Timing model MVP-A idéntico a `PaperRunner.handle_kline`
> (precio=close, atr=None, confidence=1.0, Intensity.MEDIUM).
> FINAL_HOLDOUT intacto y bloqueado por el guard existente.

- Base: `96998e6` (verificado; sin modificar implementación).
- Dataset: `BYBIT_ETHBTC_V001` · Split v1: DEV [0,62208) · WF [62208,88128) ·
  HOLDOUT [88128,103680).

## Nuevos módulos (solo `src/lab/`, runtime protegido CLEAN)

- `src/lab/frozen_dataset.py` — `FrozenDatasetAdapter`: valida dataset_id,
  SHA-256 del manifest (vs splits/v1.json) y SHA-256 del CSV (vs manifest),
  sirve el rango [start,end) como tupla inmutable de `Candle` originales
  (sin mutar, sin resamplear, sin sintéticos), exige timestamps estrictos y
  rechaza con ValueError cualquier intersección con FINAL_HOLDOUT.
- `src/lab/session_runner.py` — `LabSessionRunner`: consume el adapter,
  `strategy.on_candle` → `TradingDecision` → `PaperEngine.on_price` →
  `mark_to_market`; produce `LabSessionResult` (events + metrics + hashes,
  ligado a `experiment_spec_id`). Agregados puros en `summarize_lab_events`.
  Sin sizing/stops/fees/slippage/accounting propios.

## Paridad (no tautológica)

Misma secuencia controlada por dos caminos independientes con instancias
frescas: LabSessionRunner vs `PaperRunner.handle_kline` real (+ FakeRepo).
Comparados por vela: acción, filled, exec_price, quantity, fee, slippage,
equity, risk_reason, exit_reason. Caso [BUY,HOLD,SELL] anclado a valores
calculados a mano (qty 0.2, exec 100.02/100.9798, fees 0.04019996,
slippage 0.00804, exit `llm_sell`); caso SELL-sin-posición →
`no_position_to_reduce` en ambos; caso baseline EMA/RSI con señales reales.

## Calidad (evidencia en este directorio)

| Check | Resultado |
|---|---|
| tests/lab (184: 17C-A/B regresión + 29 nuevos 17D) | 184 passed |
| Paper/Risk/Strategy/Portfolio (8 suites) | 82 passed |
| tests/integration (PostgreSQL disponible) | 13 passed, 2 failed* |
| global `--cov=src --cov-branch --cov-fail-under=90` | 622 passed, 1 skipped, 2 failed* · **95.38%** ✔ |
| `src/lab/frozen_dataset.py` + `src/lab/session_runner.py` | 100% statements, 100% branches ✔ |
| `ruff check src/ tests/` · `ruff format --check` · `mypy src tests` (214 files) | PASS / PASS / PASS |

\* 2 failed = `tests/integration/test_memory_repository.py` (pgvector exige
384 dims, el test inserta embeddings de 4 dims) → PREEXISTING_FAILURE:
ni el test ni sus fixtures importan código `lab/*`; falla idéntico con o sin
17D. 0 errores. Con PostgreSQL caído anteriormente estos mismos quedaban como
ENVIRONMENT_BLOCKED; ahora verificados realmente.

## Baseline failure check (base limpia 96998e6, worktree aislado)

GLOBAL_SUITE_STATUS=RED_PREEXISTING_FAILURE (no escribir GLOBAL_TESTS=PASS).

Los mismos 2 tests de `tests/integration/test_memory_repository.py` fallan en
la base 96998e6 sin archivos 17D, con la misma causa (pgvector 384 vs 4):
evidencia `baseline-memory-failures.log` (2 failed, 1 passed).
PREEXISTING_FAILURE_CONFIRMED=YES · PHASE_17D_REGRESSIONS=0.

PREEXISTING_TEST_DEBT (no corregir dentro de 17D):

- tests/integration/test_memory_repository.py
- fixture embedding dimension=4
- schema pgvector dimension=384

## Holdout

`holdout/v1.state.json` → PRISTINE (verificado post-ejecución; runner y
adapter no tienen rutas de escritura). Tests 1–10 del gate: todos PASS.

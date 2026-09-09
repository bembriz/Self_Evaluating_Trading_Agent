# Commit Candidate Report — 2026-09-08 · Fase 16c.5a (Duplicate Candle State Idempotency / D3)

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> Subfase correctiva autorizada por GATE (D3). Restaura la garantía
> `NO_RESTART_TRACE == RESTART_TRACE`.

## Objetivo

Corregir el defecto **D3** (propuesta 16c §Anexo A, §4.4.c): una vela con timestamp ya
procesado volvía a avanzar estado mutable en memoria (EMA/RSI/ATR/regime/deque/engine),
rompiendo la paridad restart↔control tras un solapamiento REST/WS. La deduplicación se
implementa en el punto más temprano del pipeline (`PaperRunner.handle_candle`), **antes** de
cualquier mutación, sin depender de `PostgreSQL UNIQUE`/`ON CONFLICT` (que solo protegen
persistencia, no los trackers en RAM). No se toca la matemática de `EmaRsiBaseline`,
`AtrTracker`, `RiskEngine` ni `Portfolio`.

## Rama

| Campo | Valor |
|---|---|
| branch | `fix/phase-16c-restart-safe` |
| base commit | `49bcefd` (16c.3) |

## Contrato temporal implementado

| Condición (T vs last) | Comportamiento |
|---|---|
| `T < last` | `OutOfOrderTimestampError` (existente) |
| `T == last` + vela idéntica | `IDEMPOTENT_NO_OP` → `None` (sin mutación, sin evento, sin fill, sin persistencia) |
| `T == last` + payload distinto | `DuplicateCandleError` (nueva, flat) → STOP, no continuar trading |
| `T > last` | procesamiento normal |

## Archivos

- **Modificados:**
  - `src/application/services/paper_runner.py` (+32 / −3) — producción
  - `tests/integration/test_recovery_roundtrip.py` (+62) — test de regresión integración
- **Creados:**
  - `tests/test_duplicate_candle.py` (7 tests unitarios)
  - `docs/phases/16c/commit-candidate-005.md` (este reporte)
  - `docs/phases/16c/evidence/d3-{unit-tests,integration-tests,full-suite,ruff-check,ruff-format,mypy}.log`
  - `docs/phases/16c/evidence/d3-coverage.json`
- **Eliminados:** ninguno

## Diff

`git diff --stat` (producción + integración): 2 files, +91 / −3. Más `test_duplicate_candle.py`
(nuevo) y la evidencia D3. Sin cambios en `EmaRsiBaseline`, `AtrTracker`, `RiskEngine`, `Portfolio`,
`strategy_version` ni `risk_config_version`.

## Arquitectura afectada / blast radius

Cambio contenido en `PaperRunner`:
- `DuplicateCandleError(RuntimeError)` — excepción nueva, plana.
- `_last_candle: dict[(symbol, timeframe), Candle]` — track del último candle procesado.
- `handle_candle` — guard de orden + dedup (`<` / `==` idéntico / `==` distinto) antes de `_process`.
- `replay` — registra `_last_candle` tras cada vela (para que el restore repare el guard).

`handle_candle` retorna ahora `PaperTradeEvent | None`. Callers verificados (trace_path inbound):

| Caller | Impacto |
|---|---|
| `PaperRunner.handle_kline` | retorna `PaperTradeEvent | None` — sin cambio |
| `BackfillService.backfill` | ignora retorno — sin cambio |
| `_run_loop` (cli) | ya comprueba `if paper_event is not None` — sin cambio |
| `recover_and_handoff` (hop 2) | vía backfill — sin cambio |

## Índice del grafo

- [x] re-index (`index_repository`, fast): 2780 nodos / 12253 edges · 0 skipped · 0 parse_partial
- [x] `check_index_coverage` (`paper_runner.py`, `test_duplicate_candle.py`): `no_recorded_issue`
- [x] `tests/integration` es subárbol excluido por diseño del grafo (no `parse_partial`)
- [x] `trace_path` inbound `handle_candle`: 5 callers, todos tolerantes a `None`

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Unit D3 (`test_duplicate_candle.py`) | **7 passed** | `d3-unit-tests.log` |
| Integración D3 (`test_recovery_roundtrip.py`) | **5 passed** (1 nuevo) | `d3-integration-tests.log` |
| Full suite | **594 passed, 1 skipped** | `d3-full-suite.log` |

### Cobertura de requisitos (TDD RED→GREEN)

| Requisito | Test | Resultado |
|---|---|---|
| T == last, vela idéntica → estado completo sin cambios | `test_duplicate_same_candle_is_idempotent_noop` | PASS |
| T == last, payload distinto → STOP | `test_duplicate_different_candle_raises` | PASS |
| T < last → `OutOfOrderTimestampError` | `test_out_of_order_raises` | PASS |
| duplicado no crea evento | `test_duplicate_does_not_create_event` | PASS |
| duplicado no crea fill | `test_duplicate_buy_does_not_create_second_fill` | PASS |
| duplicado no altera contabilidad | `test_duplicate_buy_does_not_create_second_fill` (cash/pos invariantes) | PASS |
| duplicado no avanza EMA/RSI/ATR/regime | `test_duplicate_does_not_advance_trackers` | PASS |
| duplicado no incrementa processed/candles | `test_duplicate_kline_returns_none_no_processed_semantics` | PASS |
| crash-after-commit → overlap → no-op (snapshot completo) | `test_crash_after_commit_overlap_replayed_candle_is_noop` | PASS |

El test ROJO original `test_crash_after_commit_overlap_replayed_candle_is_noop` pasó de **RED** a **GREEN**
(snapshot completo: cash/position/realized + ema_fast/ema_slow/rsi + ATR + regime).

## Cobertura

**94.39%** branch (threshold 90%) — `docs/phases/16c/evidence/d3-coverage.json`. La nueva rama de
dedup en `handle_candle` queda cubierta por los tests unitarios.

## Calidad

```bash
uv run ruff check .             # All checks passed
uv run ruff format --check .    # 260 files already formatted
uv run mypy src tests           # Success: no issues found in 229 source files
uv run pytest                   # 594 passed, 1 skipped
```

## Seguridad

- [x] Sin secretos en el diff (solo código de dominio + tests)
- [x] Sin archivos `.env` ni credenciales
- [x] Sin cambios en `LIVE_TRADING_ENABLED`, fees, slippage, thresholds ni versiones de estrategia/risk

## Riesgos

- El guard se aplica por `(symbol, timeframe)`: el paper-runner actual es single-symbol (ETHUSDT 15m),
  igual que el resto del pipeline. No introduce riesgo multi-símbolo.
- El `DuplicateCandleError` no se captura en `_run_loop` (propaga y detiene el runner) — comportamiento
  intencional: inconsistencia de datos ⇒ STOP.
- `handle_candle` retorna `None` para duplicados; `_run_loop` ya lo trata como no-procesado (sin commit,
  sin `candles_processed`).

## Deuda técnica

- `test_e2e_restart_parity.py` (16c.5) requiere un `assert ... is not None` menor por el nuevo tipo de
  retorno; se pliega al commit 16c.5 (no incluido aquí).
- `application_version` sin bump (política B); `0.2.0` antes del redeploy integrado de 16c.

## Versionado

`strategy_version = baseline-v1` · `risk_config_version = risk-v1` · `application_version` sin bump.

## Mensaje de commit propuesto

```
fix(phase-16c): deduplicate already-processed candles before state mutation (D3)

- PaperRunner.handle_candle guarda orden (T < last → OutOfOrderTimestampError)
  y deduplica T == last antes de cualquier mutación de trackers/engine/portfolio
- T == last idéntico → IDEMPOTENT_NO_OP (None); payload distinto → DuplicateCandleError
- replay registra _last_candle para reparar el guard tras restore
- regresión: test_duplicate_candle.py + test_crash_after_commit_overlap_replayed_candle_is_noop
- NO_RESTART_TRACE == RESTART_TRACE restaurado; strategy/risk/fees sin cambios
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

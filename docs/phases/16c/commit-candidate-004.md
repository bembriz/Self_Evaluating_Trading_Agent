# Commit Candidate Report — 2026-09-09 · Fase 16c.5 (Integrated recovery/auditability E2E)

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

Suite E2E integrada de recovery/auditabilidad que demuestra la garantía central del paper-runner restart-safe — **`NO_RESTART_TRACE == RESTART_TRACE`** — cubriendo los escenarios E2E-1..10 del PRD §76 / propuesta 16c §14.3. Es **test-only**: no toca código de producción, estrategia, risk, fees ni thresholds.

Incorpora como requisito explícito la regresión **D3** (crash AFTER commit → replay/overlap → vela duplicada = no-op → sin evento/fill/contabilidad duplicados → paridad total de estado), ya cerrada en `6eac3c7` y cubierta por `tests/integration/test_recovery_roundtrip.py::test_crash_after_commit_overlap_replayed_candle_is_noop`. Crash BEFORE commit lo cubre `E2E-10` en esta suite.

## Rama

| Campo | Valor |
|---|---|
| branch | `fix/phase-16c-restart-safe` |
| base commit | `6eac3c7` (16c.5a — Duplicate Candle State Idempotency / D3) |

## Archivos

- **Creados:**
  - `tests/e2e/test_e2e_restart_parity.py` (10 casos E2E)
  - `docs/phases/16c/post-commit-verification-005.md` (cierre D3)
  - `docs/phases/16c/evidence/{e2e-restart-parity,full-suite-coverage,ruff-check,ruff-format,mypy}.log`
  - `docs/phases/16c/evidence/coverage.json`
  - `docs/phases/16c/evidence/log.md`
  - `docs/phases/16c/commit-candidate-004.md` (este reporte)
- **Modificados:** ninguno
- **Eliminados:** ninguno

## Diff

```text
git diff --cached --stat  →  10 files changed, 879 insertions(+)
git diff --cached --name-status  →  10 A (Added), 0 M, 0 D
```

- `tests/e2e/test_e2e_restart_parity.py` (+500)
- `docs/phases/16c/commit-candidate-004.md` (+134)
- `docs/phases/16c/post-commit-verification-005.md` (+48)
- `docs/phases/16c/evidence/full-suite-coverage.log` (+161)
- `docs/phases/16c/evidence/e2e-restart-parity.log` (+12)
- `docs/phases/16c/evidence/{ruff-check,ruff-format,mypy}.log` (+6 cada uno)
- `docs/phases/16c/evidence/log.md` (+5)
- `docs/phases/16c/evidence/coverage.json` (+1)

10 archivos nuevos, 0 modificados. Sin cambios en `src/`.

## Arquitectura afectada

**Ninguna (producción).** Cambio exclusivamente aditivo en tests + docs. Los escenarios ejercitan el pipeline real ya desplegado (`PaperRunner` → `PaperEngine` → `RiskEngine` → `Portfolio`, `replay`, `restore_runner`, `BackfillService`, `recompute_decision_contexts`) con repos in-memory y `PrecomputedStrategy` para control determinista de BUY/SELL/HOLD.

## Índice del grafo

- [x] Índice re-indexado (`index_repository`, fast): 2780 nodos / 12253 edges · 0 skipped · 0 parse_partial.
- [x] Cobertura verificada (`check_index_coverage`): `tests/e2e` es subárbol **excluido por diseño** del índice (directorio de tests). Sin símbolos de producción afectados → blast radius = 0 en `src/`.

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| E2E 16c.5 (`test_e2e_restart_parity.py`, 10 casos) | **10 passed** | `docs/phases/16c/evidence/e2e-restart-parity.log` |
| E2E completa (`tests/e2e`) | **17 passed** | incluida en full suite |
| Suite completa | **594 passed, 1 skipped** | `docs/phases/16c/evidence/full-suite-coverage.log` |

### Mapeo PRD §76 → caso E2E

| E2E | Escenario | Test | Resultado |
|---|---|---|---|
| E2E-1 | Restart mid-position (paridad total de estado + residual 0) | `test_e2e_1_restart_mid_position_full_state_parity` | PASS |
| E2E-2 | Restart daily-loss (estado preservado + BUY bloqueado) | `test_e2e_2_restart_daily_loss_preserved` | PASS |
| E2E-3/4 | Market evidence + no-lookahead (recompute==snapshot) | `test_e2e_3_4_market_evidence_and_no_lookahead` | PASS |
| E2E-5 | Métricas requeridas tras corrida completa | `test_e2e_5_required_metrics_after_full_run` | PASS |
| E2E-6/7/8 | Restart con gap 0/1/N (paridad, sin duplicados) | `test_e2e_6_7_8_restart_gap_recovery_parity[0,1,3]` | PASS |
| E2E-9 | Overlap REST/WS idempotente | `test_e2e_9_reprocess_overlap_is_idempotent` | PASS |
| E2E-10 | Crash ANTES del commit recuperado vía backfill | `test_e2e_10_crash_before_commit_recovers_via_backfill` | PASS |
| MUST_HAVE | Kill switch sobrevive restart y bloquea BUY | `test_e2e_kill_switch_survives_restart_and_blocks_buy` | PASS |

### Garantía crash-before + crash-after

| Caso | Cobertura | Resultado |
|---|---|---|
| Crash **BEFORE** commit | `test_e2e_10_crash_before_commit_recovers_via_backfill` (esta suite) | PASS |
| Crash **AFTER** commit (D3) | `test_crash_after_commit_overlap_replayed_candle_is_noop` (integración, commit `6eac3c7`) | PASS |

Crash AFTER: vela committeada reaparece por replay/overlap → vela duplicada = no-op → sin evento duplicado,
sin fill duplicado, sin doble contabilidad, paridad total de estado (`_engine_snapshot` completo:
cash/position/realized + ema_fast/ema_slow/rsi + ATR + regime).

## Cobertura

**94.39%** branch (threshold 90%) — `docs/phases/16c/evidence/coverage.json`. Test-only, no reduce cobertura.

## Calidad

```bash
uv run ruff check .             # All checks passed!
uv run ruff format --check .    # 260 files already formatted
uv run mypy src tests           # Success: no issues found in 229 source files
uv run pytest                   # 594 passed, 1 skipped
```

## Seguridad

- [x] Secret scan limpio (0 coincidencias reales; solo docstrings/test anti-secretos)
- [x] Sin archivos `.env` ni credenciales
- [x] Sin cambios en `LIVE_TRADING_ENABLED`, fees, slippage ni thresholds

## Riesgos

- Los tests usan `PrecomputedStrategy` (estrategia de dominio versionada) para control determinista de señales; la paridad con la estrategia real `EmaRsiBaseline` ya está cubierta en `tests/integration/test_recovery_roundtrip.py` (PostgreSQL).
- `tests/e2e` queda fuera del índice del grafo por diseño; la cobertura de estos escenarios se demuestra por ejecución verde, no por el grafo.

## Deuda técnica

- 16c.4 (nuevo gate Paper operacional) sigue pendiente de aprobación del usuario; no bloquea esta suite.
- `application_version` sin bump (política B); `0.2.0` antes del redeploy integrado de 16c.

## Mensaje de commit propuesto

```
test(phase-16c): E2E integrada de recovery/auditabilidad (E2E-1..10)

- tests/e2e/test_e2e_restart_parity.py: paridad NO_RESTART_TRACE == RESTART_TRACE
  (restart mid-position, daily-loss, market evidence, no-lookahead, métricas,
  gap 0/1/N, overlap REST/WS, crash-before, kill switch MUST_HAVE)
- crash-after-commit (D3) referenciado desde test_recovery_roundtrip.py (6eac3c7)
- repos in-memory + motor real; sin red externa ni LLM real
- evidencia: 594 passed, 1 skipped; cobertura 94.39%
- sin cambios en src/ (estrategia/risk/fees sin cambios)
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

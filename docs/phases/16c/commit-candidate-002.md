# Commit Candidate Report — 2026-09-08 · Fase 16c.2 (Market + decision evidence)

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

Añadir **decision_context JSONB versionado** al `paper-runner`: persistir lo que vio la estrategia en cada decisión (indicadores, regime, signal_reason) y un **helper de recompute no-lookahead** que demuestra causalidad (`recompute(T) == snapshot(T)`). No cambia estrategia, RiskEngine, fees/slippage ni thresholds.

## Rama

| Campo | Valor |
|---|---|
| branch | `fix/phase-16c-restart-safe` |
| base commit | `0350839` (16c.1 Restart-safe recovery) |

## Archivos

- **Creados:**
  - `migrations/versions/0011_paper_events_decision_context.py`
  - `src/application/services/decision_context.py`
  - `tests/test_decision_context.py`
  - `tests/test_decision_context_no_lookahead.py`
  - `tests/integration/test_migration_0011.py`
  - `docs/phases/16c/post-commit-verification-001.md` (doc de cierre 16c.1)
  - `docs/phases/16c/commit-candidate-002.md` (este reporte, incluido en el commit)
- **Modificados:**
  - `src/application/ports/paper_trading.py` (`PaperTradeEvent.decision_context`)
  - `src/application/services/paper_runner.py` (`_process` construye context; `events_equivalent` compara context)
  - `src/domain/trading/strategy.py` (`EmaRsiBaseline.ema_fast/ema_slow/rsi`)
  - `src/infrastructure/database/models.py` (`decision_context` JSONB)
  - `src/infrastructure/database/repositories.py` (persist/load context)
  - `tests/integration/test_recovery_roundtrip.py`
- **Eliminados:** ninguno

## Diff

`git diff --cached --stat`: **13 files changed, 604 insertions(+), 5 deletions(-)**.

> `commit-candidate-002.md` **sí forma parte del propio commit** (convención del repo, igual que 16c.1).

## Arquitectura afectada

- `DecisionContext` (nuevo, application): dataclass versionado + `validate_decision_context` + `recompute_decision_contexts` (no-lookahead).
- `EmaRsiBaseline` (domain): expone `ema_fast`/`ema_slow`/`rsi` (solo lectura; no cambia lógica de señal).
- `PaperRunner._process`: captura regime/ATR/EMA/RSI/signal_reason y persiste el snapshot.
- `events_equivalent`/`replay`: ahora verifica también `decision_context` (recovery consistente).
- `paper_trade_events.decision_context` (JSONB, migración 0011).

## Índice del grafo

- [x] re-index: proyecto `tmp-opencode-phase-16c-restart-safe` (2671 nodos / 11663 edges, 0 skipped/parse_partial)
- [x] `detect_changes` since `0350839`: 11 changed_files · 113 seed_symbols · 179 impacted
- [x] `check_index_coverage` (6 archivos core): `no_recorded_issue` en todos

Blast radius amplio (esperado): `strategy.py`/`paper_runner.py` son dependencias transversales (backtest, replay, paper_session, ml_pipeline).

## Tests ejecutados

| Suite | Resultado |
|---|---|
| Unit + Integration | **552 passed, 1 skipped** |

### Tests mínimos obligatorios (nombre → PASS)

| Requisito | Test | Resultado |
|---|---|---|
| candle→indicators→signal→event→context persisted | `test_decision_context_persisted_and_roundtrips` (integration) | PASS |
| context JSONB round-trip | `test_decision_context_jsonb_roundtrip` + `_preserves_nones` | PASS |
| schema_version validation | `test_validate_decision_context_{accepts,rejects_wrong,rejects_missing,rejects_non_dict,rejects_missing_signal_reason}` | PASS |
| recompute(T) == persisted_snapshot(T) | `test_recompute_equals_persisted_snapshot` | PASS |
| truncated_dataset_at_T == full_dataset_decision_at_T | `test_truncated_dataset_equals_full_dataset_at_T` + `test_recompute_decision_at_T_uses_only_past_candles` | PASS |
| mutating T+1..N no cambia decision(T) | `test_mutating_future_candles_does_not_change_decision_at_T` | PASS |
| restart recovery usa evidencia persistida | `test_restart_parity_mid_position` (replay ahora compara context) | PASS |
| no duplicated context/event on reprocessing | `test_backfill_overlap_reprocess_is_idempotent` + `test_paper_event_idempotent_add` | PASS |
| migración 0010↔0011 roundtrip (up/down) | `test_migration_0011_roundtrip` | PASS |

## Cobertura

`TOTAL 92%` (branch; `--cov-fail-under=90` OK). `decision_context.py` **100%**, `strategy.py` **100%**.

## Calidad

```bash
uv run ruff check .             # All checks passed
uv run ruff format --check .    # 253 files already formatted
uv run mypy src tests           # Success: no issues found in 222 source files
uv run pytest                   # 552 passed, 1 skipped
```

## Seguridad

- [x] Sin secretos en el diff
- [x] Sin archivos .env ni credenciales
- [x] Sin cambios en `LIVE_TRADING_ENABLED`, fees, slippage ni thresholds

## Riesgos

- `decision_context` es un snapshot causal (construido tras procesar la vela T); el recompute usa trackers frescos en el mismo orden, garantizando no-lookahead por construcción.
- `events_equivalent` compara context con tolerancia float (1e-9) para indicadores, evitando falsos STOP por redondeo.

## Deuda técnica

- Prometheus/scrape y logging JSON quedan para 16c.3.
- `application_version` sin bump (política B); `0.2.0` obligatorio antes del redeploy integrado de 16c.

## Versionado

`strategy_version = baseline-v1` · `risk_config_version = risk-v1` · `application_version` sin bump.

## Mensaje de commit propuesto

```
feat(phase-16c): decision_context JSONB + no-lookahead recompute

- decision_context JSONB versionado (schema_version=1) en paper_trade_events
- snapshot causal por decisión: signal_reason, ATR, EMA20/50, RSI, regime
- recompute_decision_contexts: helper no-lookahead (contexto en T usa solo velas <= T)
- EmaRsiBaseline expone ema_fast/ema_slow/rsi (solo lectura)
- events_equivalent/replay verifican también el decision_context
- strategy_version/risk_config_version sin cambios
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

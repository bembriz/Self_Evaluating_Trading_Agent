# Commit Candidate Report — 2026-09-08 · Fase 16c.1

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

Hacer el `PaperRunner` **restart-safe**: recovery determinista por event replay, persistencia atómica idempotente (candle + evento por vela), gap backfill con handoff REST→WS sin ventana de pérdida, kill switch persistente (MUST_HAVE) y runtime 45/0 con preflight. Es la primera subfase de la Fase 16c (`INVALIDATE_AND_FIX` de la auditoría Day-1). **No** cambia `baseline-v1` ni `risk-v1` ni fees/slippage.

## Rama

| Campo | Valor |
|---|---|
| branch | `fix/phase-16c-restart-safe` |
| base commit | `9fecca6` (fix/phase-16b-paper-runner-atr) |

## Archivos

- **Creados:**
  - `migrations/versions/0009_market_candles_paper_source.py`
  - `migrations/versions/0010_paper_trade_events_idempotency.py`
  - `src/application/services/backfill.py`
  - `src/application/services/recovery.py`
  - `tests/test_runtime_preflight.py`, `tests/test_recovery.py`, `tests/test_backfill.py`, `tests/test_recovery_orchestration.py`, `tests/integration/test_recovery_roundtrip.py`
  - `docs/superpowers/plans/2026-09-08-phase-16c-restart-safe-recovery.md`
- **Modificados:**
  - `src/settings.py` (`paper_max_runtime_days` 7→45)
  - `src/application/ports/market_repositories.py` (métodos paper-live)
  - `src/application/services/paper_runner.py` (`_process`/`handle_candle`/`replay`/`events_equivalent` + kill switch)
  - `src/domain/risk/guards.py` (`KillSwitchState.to_dict/from_dict`)
  - `src/infrastructure/database/models.py` (MarketCandle partial unique + PaperTradeEvent unique)
  - `src/infrastructure/database/repositories.py` (upsert_paper/session_range/last_persisted_ms + event upsert)
  - `src/interfaces/cli/paper_runner.py` (preflight + resolve_runtime + restore + handoff)
  - `tests/test_settings.py`, `tests/test_cli_paper_runner.py`, `tests/test_paper_runner.py`, `tests/test_risk_guards.py`
- **Eliminados:** ninguno

## Diff

`git diff --cached --stat`: **24 files changed, 1814 insertions(+), 25 deletions(-)**.

## Arquitectura afectada

- `PaperRunner` (application): extrae `_process` puro; añade `handle_candle` (persistencia atómica) y `replay` (verificación determinista).
- `PaperEngine`/`Portfolio`/`RiskEngine`/`EmaRsiBaseline`/`AtrTracker`/`RegimeClassifier`: **sin cambios** (deterministas, usados por replay).
- `repositories`/`models`/migraciones: `market_candles` partial unique (download vs paper-live) + `paper_trade_events` unique idempotency key.
- CLI: `preflight_runtime` + `resolve_runtime_seconds` + `restore_runner` + `recover_and_handoff`.

## Índice del grafo

- [x] Índice re-indexado (`index_repository`) — proyecto `tmp-opencode-phase-16c-restart-safe` (2632 nodos, fast)
- [x] `detect_changes` since `9fecca6`: 24 changed_files · 240 seed_symbols · 134 impacted
- [x] `check_index_coverage` sobre 9 archivos tocados → `no_recorded_issue` en todos
- [x] `trace_path` (`restore_runner` inbound/outbound) → callers: `cli.paper_runner._run`; callees: `replay`→`_process`→`events_equivalent`/`Recovery*Error`

## Tests ejecutados

| Suite | Resultado |
|---|---|
| Unit (`--ignore=tests/integration`) | 521 passed, 1 skipped |
| Integration (Postgres 5433) | 19 passed (incl. `test_restart_parity_mid_position`) |
| **Total** | **540 passed, 1 skipped** |

### Tests críticos (nombre → PASS)

| Escenario | Test | Resultado |
|---|---|---|
| restart mid-position parity | `test_restart_parity_mid_position` | PASS |
| commit failure → STOP/rollback | `test_run_loop_stops_on_commit_failure` | PASS |
| restart sin gap | `test_restart_no_gap_produces_no_new_events` | PASS |
| gap de 1 vela | `test_backfill_one_lost_candle` | PASS |
| gap de N velas | `test_backfill_multiple_lost_candles_in_order` | PASS |
| REST/WS handoff race | `test_handoff_race_candle_closes_between_backfill_and_subscribe` | PASS |
| overlap REST/WS exactly-once | `test_backfill_overlap_reprocess_is_idempotent` | PASS |
| open/unconfirmed REST candle ignorada | `test_backfill_skips_partial_candle` | PASS |
| kill switch survives restart | `test_restore_runner_restores_kill_switch` + `test_kill_switch_state_serialization_roundtrip` | PASS |
| runtime=45 PASS | `test_preflight_allows_minimum_runtime` | PASS |
| runtime=0 unlimited PASS | `test_run_paper_runner_zero_days_means_unlimited` + `test_resolve_runtime_seconds_zero_days_means_unlimited` | PASS |
| runtime<45 preflight FAIL | `test_preflight_rejects_short_runtime_when_certifying` | PASS |

## Cobertura

`TOTAL 92%` (branch; `--cov-fail-under=90` OK). Nuevos módulos a 100%: `backfill.py`, `recovery.py`, `guards.py`.

## Calidad

```bash
uv run ruff check .             # All checks passed
uv run ruff format --check .    # 249 files already formatted
uv run mypy src tests           # Success: no issues found in 219 source files
uv run pytest                   # 540 passed, 1 skipped
```

## Seguridad

- [x] Sin secretos en el diff (grep de api_key/password/token/private key → 0 coincidencias reales)
- [x] Sin archivos .env ni credenciales
- [x] `LIVE_TRADING_ENABLED=false` invariante (reforzado por `validate_safe`)

## Riesgos

- El recovery reconstruye estado por replay y **detiene** ante divergencia (no sustituye fills). Si el replay no reproduce el estado persistido, el runner aborta en lugar de continuar con estado inconsistente.
- El handoff REST→WS cierra la carrera con un segundo backfill tras la suscripción.
- Migraciones aditivas y reversibles (up/down verificados en `test_schema_migrado`).

## Deuda técnica

- `decision_context` (JSONB) y no-lookahead recompute quedan para 16c.2.
- Prometheus/scrape y logging JSON quedan para 16c.3.

## Versionado (política propuesta: B)

- **`application_version` permanece sin bump en este commit** (16c.1 es commit interno no desplegable).
- `0.2.0` será **obligatorio** antes del commit/redeploy integrado de Fase 16c.
- Se mantienen: `strategy_version = baseline-v1`, `risk_config_version = risk-v1`.

## Mensaje de commit propuesto

```
fix(phase-16c): paper-runner restart-safe recovery

- recovery determinista por event replay con verificación contra fills persistidos
  (STOP ante divergencia/gap; no sustituye ejecución histórica)
- persistencia atómica idempotente por vela: market_candle + paper_trade_event en
  una transacción, con unique key (session, symbol, timeframe, timestamp_ms)
- market_candles: partial unique por procedencia (download vs paper-live, session-scoped)
- gap backfill desde Bybit REST con handoff sin ventana de pérdida (solo velas cerradas)
- kill switch persistente (MUST_HAVE) vía system_state
- paper_max_runtime_days=45 (0=unlimited) + preflight de certificación
- strategy_version/risk_config_version sin cambios
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

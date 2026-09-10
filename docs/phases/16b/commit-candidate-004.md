# Commit Candidate Report — Fix permanente paper_stale_timeout_seconds (0.1.3)

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

Corregir el falso "stale" detectado en el redeploy 0.1.2: el paper-runner heredaba `stale_timeout_seconds=10s` (diseñado para el order-book), pero Bybit documenta **push frequency 1–60s** para Kline WebSocket. El stream `kline.15.ETHUSDT` presenta gaps reales de 20–32s, lo que provocaba falsas detecciones de stale y reconexiones innecesarias (~1/min).

## Rama

| Campo | Valor |
|---|---|
| branch | `fix/phase-16b-paper-runner-atr` |
| base commit | `c832382` |

## Archivos

- **Modificados:**
  - `src/settings.py` — nueva `paper_stale_timeout_seconds: float = 120.0` (independiente de `stale_timeout_seconds`)
  - `src/interfaces/cli/paper_runner.py` — usa `settings.paper_stale_timeout_seconds` (1 línea)
  - `src/version.py` — `0.1.2 → 0.1.3`
  - `.env.example` — documenta `PAPER_STALE_TIMEOUT_SECONDS=120`, `PAPER_METRICS_HOST`, `PAPER_METRICS_PORT`
  - `tests/test_settings.py` — 2 tests nuevos
  - `tests/e2e/test_e2e_ws_observability.py` — 1 test nuevo (gap < timeout → NO stale)

## Aislamiento del order-book

`stale_timeout_seconds` (10s) **permanece intacto** y sigue siendo usado por `market_worker`/`market_data_service` (order-book). El paper-runner usa exclusivamente `paper_stale_timeout_seconds`.

## Tests (TDD RED→GREEN)

| Requisito | Test | Resultado |
|---|---|---|
| gap < 120s → NO stale | `test_e2e_ws_gap_below_timeout_does_not_stale` (gap < timeout) | PASS |
| gap > 120s → stale + reconnect | `test_e2e_ws_stale_detection_marks_and_recovers` (gap > timeout) | PASS |
| Kline gap 60s → NO stale | cubierto por "gap < timeout" + default 120s | — |
| paper-runner usa `paper_stale_timeout_seconds` | `test_paper_stale_timeout_defaults_keep_orderbook_unchanged` + wiring | PASS |
| market_worker sigue con `stale_timeout_seconds` | mismo test (assert `stale_timeout_seconds==10.0`) | PASS |
| config/env override | `test_paper_stale_timeout_env_override` | PASS |

## Suite / Calidad

- Suite completa: **505 passed, 1 skipped** (skip = `RUN_MODEL_SMOKE`).
- Cobertura: **94.47%** (branch 94%).
- Ruff / Mypy: limpios / 0 issues (212).

## Versiones

- `strategy_version = baseline-v1` (sin cambio)
- `risk_config_version = risk-v1` (sin cambio)
- `application_version = 0.1.2 → 0.1.3`

## Seguridad / Deploy

- Sin secretos. Sin cambios de estrategia/riesgo/thresholds.
- **Redeploy 0.1.3:** eliminar el override provisional `STALE_TIMEOUT_SECONDS=120` de `compose.yaml` en lenovosrv y reemplazarlo por `PAPER_STALE_TIMEOUT_SECONDS=120` (para no alterar el order-book).

## Riesgos

- Ninguno nuevo; timeout de stale de 120s es conservador para el kline (push 1–60s).

## Rollback

`git revert <commit>` (solo config + test; sin migraciones).

## Mensaje de commit propuesto

```
fix(observability): dedicated paper_stale_timeout_seconds for kline stream

- settings: paper_stale_timeout_seconds=120.0 (kline push frequency 1-60s); deja
  stale_timeout_seconds=10.0 intacto para el order-book/market_worker
- paper_runner: usa settings.paper_stale_timeout_seconds en el wait_for de recv
- .env.example: documenta PAPER_STALE_TIMEOUT_SECONDS / PAPER_METRICS_HOST/PORT
- version 0.1.2 -> 0.1.3 (strategy=baseline-v1, risk-v1 sin cambios)
- tests: defaults/env override + E2E gap<timeout no-stale
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

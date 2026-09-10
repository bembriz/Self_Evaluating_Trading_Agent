# Commit Candidate Report — 2026-09-06 (Fase 16b)

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

Corregir la fase 16b en la rama desplegable (`fix/phase-16b-paper-runner-atr`, base = rama paper):

1. **`atr=None` en el runner WS** (causa raíz del 0-trades): el Risk Engine rechazaba todo BUY con `stop_unavailable` → 0 fills → equity congelada → certificación estancada.
2. **`ws.close()`** tras conexión nunca establecida lanza `AttributeError` (websockets 17) y enmascara el error primario de red.
3. **Paridad paper↔replay**: `AtrTracker` incremental reproduce vela a vela la serie de `atr()`.
4. **`--session-id` / `PAPER_SESSION_ID`** para arrancar una corrida nueva con la misma `strategy_version` (requisito de reinicio).
5. **`paper_certification --invalidate`** para marcar la corrida 2026-09-02→06 como INVALIDATED (archiva snapshot + resetea el estado activo).

## Rama

| Campo | Valor |
|---|---|
| branch | `fix/phase-16b-paper-runner-atr` |
| base commit | `187d1f7` (= `feature/paper-regime-certification`, lo desplegado) |

## Archivos

- **Creados:** `tests/test_atr_tracker.py`, `docs/phases/16b/evidence/*`, `docs/phases/16b/commit-candidate-001.md`
- **Modificados:** `.env.example`, `harness/scripts/paper_certification.py`, `harness/tests/test_paper_certification.py`, `src/application/services/paper_runner.py`, `src/domain/market/indicators.py`, `src/infrastructure/bybit/ws.py`, `src/interfaces/cli/paper_runner.py`, `src/interfaces/cli/paper_session.py`, `src/settings.py`, `tests/test_bybit_ws.py`, `tests/test_cli_paper_runner.py`, `tests/test_paper_runner.py`
- **Eliminados:** —

## Diff

```bash
12 files changed, 479 insertions(+), 18 deletions(-)
# diff completo: git -C /tmp/opencode/phase-16b-paper-runner-atr diff
```

## Arquitectura afectada

- `domain/market/indicators.py`: `AtrTracker` (nuevo, ~43 líneas) — algoritmo ATR Wilder incremental, causal, sin ventana; misma siembra SMA/recurrencia que `atr()`.
- `application/services/paper_runner.py`: `PaperRunner.handle_kline` pasa `atr=self._atr_trackers[symbol].update(candle)` en vez de `atr=None`; trackers por símbolo.
- `interfaces/cli/paper_session.py`: usa `AtrTracker` (replay) → paridad con el flujo WS.
- `infrastructure/bybit/ws.py`: `connect()` descarta el context manager si `__aenter__` falla; `close()` idempotente y tolerante a conexión nunca establecida.
- `interfaces/cli/paper_runner.py` + `settings.py`: `resolve_session_id()` (override CLI/env > derivación `paper-baseline-<tf>-<symbol>`).
- `harness/scripts/paper_certification.py`: `invalidate_state`, `reset_certification_state`, `--invalidate/--reason/--archive`; `evaluate_state` respeta `status=INVALIDATED` persistido.

**Blast radius:** consumidores de `atr()` y de `BybitWebSocketClient.close/connect`, runner WS, `paper_session`, herramienta de certificación. El índice del grafo refleja el estado commiteado (rama paper/phase-08), no el WIP sin commitear de este worktree; re-indexar tras el commit (regla §4.13).

## Índice del grafo

- [ ] Índice re-indexado tras el commit (`index_repository`) — pendiente (regla §4.13)
- [ ] Cobertura verificada sobre archivos tocados (`check_index_coverage`) — pendiente

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Focus ATR/ws/paridad/session-id (4 ficheros) | PASS (55) | `docs/phases/16b/evidence/fix-atr-ws-paridad-tests.log` |
| session-id override | PASS (16) | `docs/phases/16b/evidence/session-id-override-tests.log` |
| paper_certification --invalidate | PASS (18) | `docs/phases/16b/evidence/invalidate-paper-certification-tests.log` |
| Suite unit producto (tests/, sin integration) | PASS | `docs/phases/16b/evidence/unit-suite-fase16b.log` |
| Harness (sin `test_gen_pdf.py`, ver riesgos) | PASS | `docs/phases/16b/evidence/invalidate-paper-certification-tests.log` |
| ruff check + format | PASS | `docs/phases/16b/evidence/ruff-check-fase16b.log` |
| mypy (6 ficheros src tocados) | PASS | `docs/phases/16b/evidence/mypy-fase16b.log` |

## Cobertura

`coverage-unit-suite-fase16b.log`: **92.56% total · 93% branch** (`--cov=src --cov-branch` sobre `tests/` sin integration). Umbral 90% superado en scope unit. `indicators.py` 100%, `bybit/ws.py` 90%. `interfaces/cli/paper_runner.py` 77% (rutas live `_run` DB/WS y entrypoint no cubiertas por unit; se cubren en integration/E2E con DB).

## Calidad

```bash
ruff check .          # PASS (incluye todos los ficheros del diff)
ruff format --check . # PASS
mypy                  # PASS en los 6 ficheros src tocados
pytest                # ver tabla de evidencias
```

## Seguridad

- [x] Sin secretos en el diff (scan de `api_key|secret|password|token|BEGIN PRIVATE|postgres://|DEEPSEEK_API|BYBIT_API`)
- [x] Sin archivos `.env` ni credenciales (solo `.env.example` con `PAPER_SESSION_ID` vacía)
- [x] Secret scanning limpio

## Riesgos

- Cambio en el código que corre en producción (paper-runner en `lenovosrv`) → el redeploy exige **nueva corrida con session-id propio, misma `strategy_version`** y UAT; no se toca la versión en Paper Trading sin gate (regla arnés).
- `test_gen_pdf.py` falla en el venv de este worktree por dev-deps `markdown`/`weasyprint` ausentes → **no es regresión**; su instalación exige Dependency Proposal + aprobación (no incluida aquí).
- Cobertura de integration/E2E (PostgreSQL/WS real) pendiente de ejecutar con DB (server o compose local).

## Deuda técnica

- Evidencia duplicada entre el worktree (rama fix) y la raíz `feature/phase-08-llm-decision-agent` hasta que se integren las ramas.
- El ledger de fase 16b (entregables 1–5 = done) y su scaffolding de arnés viven como cambios sin commitear en la rama `feature/phase-08-llm-decision-agent` (commit de gobernanza aparte).
- `paper_runner._run` (110–154) sin cobertura unit directa (requiere DB+WS); cubierto por integration/E2E en servidor.

## Mensaje de commit propuesto

```
fix(phase-16b): ATR en paper-runner WS + ws.close tolerante + invalidación/reinicio de certificación

- AtrTracker incremental (Wilder) con paridad exacta vs atr(); paper_runner WS y
  paper_session lo usan (antes atr=None → Risk Engine rechazaba todo BUY con
  stop_unavailable → 0 fills → certificación estancada)
- BybitWebSocketClient: close() idempotente y tolerante a conexión nunca establecida
  (websockets 17 lanza AttributeError en __aexit__ y enmascara el error primario)
- paper-runner: --session-id / PAPER_SESSION_ID para arrancar nueva corrida con la
  misma strategy_version (deliverable session-id-override)
- paper_certification: --invalidate/--reason/--archive (archiva snapshot INVALIDATED
  y resetea el estado activo); evaluate_state respeta status persistido
- tests: paridad tracker==atr(), warmup, ws connect/close fallidos, fills tras
  warmup, precedencia session-id, invalidate CLI; ruff/mypy verdes
- evidencias en docs/phases/16b/evidence/
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

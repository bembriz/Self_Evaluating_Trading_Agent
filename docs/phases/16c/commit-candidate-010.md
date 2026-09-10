# Commit Candidate Report — 2026-09-10 · 16c.8 Fresh Session Bootstrap + Certification Boundary

> Obligatorio antes de `git commit` (PRD §65-66). Estado: **READY_FOR_USER_COMMIT_GATE**
> (no se ha ejecutado commit/push/merge).

## Objetivo

Cerrar el **BLOCKER PRE-DEPLOY** descubierto en `FINAL_DEPLOY_SHA` (`47acd2e…`):

1. **Fresh Session Bootstrap:** una sesión sin velas persistidas NO debe recuperar histórico
   REST (`last is None → start=0 → fetch histórico → decisiones/fills pre-anchor`).
2. **Certification Boundary:** el START de certificación exige una sesión **prístina**
   (0 `paper_trade_events`, 0 `market_candles`); con evidencia previa ⇒ fail-closed.
3. **Orden:** `_run` ancla el START **antes** de `recover_and_handoff` (nada de evidencia
   pre-anchor).
4. **Modelo de deployment:** sesión de validación ≠ sesión de certificación; rollback y
   pg_dump corregidos.

## Rama / base

| Campo | Valor |
|---|---|
| branch | `fix/fresh-session-certification-boundary` |
| base | `47acd2edeed93debb67c396f84e301b6c8a0ea0a` (`FINAL_DEPLOY_SHA`) |
| PR destino | `feature/phase-08-llm-decision-agent` (tras este commit) |

## Archivos

- **Creados:** `docs/phases/16c/commit-candidate-010.md` (este reporte).
- **Modificados:**
  - `src/application/services/backfill.py`
  - `src/application/services/certification_snapshot.py`
  - `src/interfaces/cli/paper_runner.py`
  - `tests/test_backfill.py`
  - `tests/test_certification_snapshot.py`
  - `tests/test_cli_paper_runner.py`
  - `compose.yaml`
  - `.env.example`
  - `docs/phases/16c/deployment-apply-plan-0.2.0.md`
- **Eliminados:** ninguno.

## Diff

```text
 .env.example                                       |   4 +-
 compose.yaml                                       |   6 +-
 docs/phases/16c/deployment-apply-plan-0.2.0.md     | 135 ++++++++++++++++----
 src/application/services/backfill.py               |  12 +-
 src/application/services/certification_snapshot.py |  15 +++
 src/interfaces/cli/paper_runner.py                 |  42 ++++--
 tests/test_backfill.py                             |  48 ++++++-
 tests/test_certification_snapshot.py               |  10 ++
 tests/test_cli_paper_runner.py                     | 141 +++++++++++++++++++++
 9 files changed, 376 insertions(+), 37 deletions(-)
```

Cambios de producto clave:
```diff
# backfill.py
         last = await self._candle_repo.last_persisted_ms(session_id, symbol, timeframe)
-        start = last + timeframe.minutes * _MS_PER_MINUTE if last is not None else 0
+        if last is None:
+            return BackfillResult(recovered=0, skipped_partial=0)   # fresh session: sin fetch
+        start = last + timeframe.minutes * _MS_PER_MINUTE

# certification_snapshot.py (nuevo)
+def pristine_session_conflict(prior_event_count: int, prior_candle_count: int) -> str | None:
+    if prior_event_count > 0:
+        return f"session has {prior_event_count} prior paper_trade_events"
+    if prior_candle_count > 0:
+        return f"session has {prior_candle_count} prior market_candles"
+    return None

# paper_runner.py (_operator_start_anchor)
+    conflict = pristine_session_conflict(prior_event_count, prior_candle_count)
+    if conflict is not None:
+        ... reject, return False

# paper_runner.py (_run): START ANTES de recover_and_handoff
-        await recover_and_handoff(...)
-        state_path = ...; startup_events = ...; artifact = ...; if start_certification: _operator_start_anchor(...)
+        state_path = ...; startup_events = ...; artifact = ...
+        if start_certification: _operator_start_anchor(..., prior_event_count=..., prior_candle_count=...)
+        await recover_and_handoff(...)
```

## Arquitectura afectada

- **Dominio:** sin cambios (0 en `src/domain`). No se toca la matemática de trading/risk.
- **Aplicación:** `BackfillService.backfill` (guard fresh session); `certification_snapshot`
  (predicado puro `pristine_session_conflict`).
- **Interfaces:** `_operator_start_anchor` (gate fail-closed) y `_run` (reorden START↔recovery).
- **Config/deployment:** `compose.yaml` (sesión de validación), `.env.example`, plan de APPLY.
- **Blast radius (codebase-memory `detect_changes`, direction=both):** 9 changed files ·
  **14 seed symbols · 104 impacted** (transitivo; incluye callers/callees de wiring y tests).
  Los hits en `src/domain` (5) son lecturas (`RiskConfig`, `KillSwitch`, `guards`), no cambios.

## Índice del grafo

- [x] Índice re-indexado (`index_repository`, moderate): **3096 nodos / 14447 edges**, 0 skipped/parse_partial.
- [x] Cobertura verificada (`check_index_coverage`): `no_recorded_issue` en `src/**` y tests;
  `docs/` excluido por diseño.

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| RED→GREEN focused (backfill/cli/snapshot) | **115 passed** | esta sesión |
| `tests/test_backfill.py` (fresh + last+interval) | PASS | esta sesión |
| `tests/e2e/test_e2e_restart_parity.py` (recovery E2E) | **10 passed** | esta sesión |
| `tests/e2e/test_certification_state_v2_e2e.py` (certification E2E) | **9 passed** | esta sesión |
| Full product suite + coverage | **727 passed, 1 skipped** | `full-suite.txt` |
| Harness suite + coverage | **91 passed** | `harness-suite.txt` |
| strict JSON (E2E case8) | PASS | `test_certification_state_v2_e2e.py` |

## Cobertura

- Producto: **93.66%** (branch) ≥ 90% (TOTAL 5240 stmts / 266 miss).
- Arnés: **80.25%** ≥ 80%.

## Calidad

```bash
uv run ruff check .          # All checks passed!
uv run ruff format --check . # 268 files already formatted
uv run mypy src tests        # Success: no issues found in 235 source files
cd harness && uv run ruff check . && uv run ruff format --check .   # All checks passed! / 24 files
uv run pytest                # 727 passed, 1 skipped
```

## Seguridad

- [x] Sin secretos en el diff
- [x] Sin archivos `.env` reales (solo `.env.example`)
- [x] `LIVE_TRADING_ENABLED=false`; sin cambios de credenciales

## Riesgos

- El reorden START↔recovery cambia el wiring de `_run` (no cubierto por unit puro de `_run`);
  validado por la suite completa + E2E de recovery/certificación.
- `pristine_session_conflict` aplica solo a NOT_STARTED/INVALIDATED; RUNNING sigue siendo no-op
  (restart de una certificación en curso no se ve afectado).
- El cambio de `PAPER_SESSION_ID` default a `paper-validation-…` es solo el default de deploy;
  la sesión de certificación se inyecta en el START.

## Deuda técnica

- `_run` sigue sin test unitario directo (requiere engine/streams); cubierto por integración/E2E.
- `config/paper.yaml` continúa sin cargarse (fuera de alcance).

## Mensaje de commit propuesto

```
fix(phase-16c): fresh session bootstrap + certification boundary

- backfill: last is None ⇒ sin fetch histórico (fresh session); recovery normal
  recupera solo el gap last+interval
- certification_snapshot: pristine_session_conflict (0 events / 0 candles)
- _operator_start_anchor: START fail-closed sobre sesión no prístina
  (NOT_STARTED/INVALIDATED); RUNNING ⇒ no-op
- _run: START se ancla ANTES de recover_and_handoff (sin evidencia pre-anchor)
- compose/.env.example: sesión de validación separada de la de certificación
- deployment-apply-plan: validación≠certificación, rollback con config 0.1.3 previa
  + pg_dump, UID/GID detectados (no asumidos)
- tests TDD: fresh session, last+interval, prior events/candles rejected,
  RUNNING preserva ancla, INVALIDATED exige sesión limpia
- sin cambios en la matemática de dominio; Paper sigue NOT CERTIFIED
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

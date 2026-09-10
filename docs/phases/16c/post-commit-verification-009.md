# Post-Commit Verification — 16c.8 (Fresh Session Bootstrap + Certification Boundary)

> **Estado:** POST_COMMIT_PASS · **Paper NO CERTIFIED**
> **Commit:** `9ae885995db8e28d23979c9a8877ab5e9b61ec85`
> **Rama:** `fix/fresh-session-certification-boundary` · **Base:** `47acd2edeed93debb67c396f84e301b6c8a0ea0a` (`FINAL_DEPLOY_SHA`)
> **Fecha:** 2026-09-10 (UTC)

## Commit

| Campo | Valor |
|---|---|
| hash | `9ae885995db8e28d23979c9a8877ab5e9b61ec85` |
| mensaje | `fix(paper): enforce fresh certification session boundary` |
| archivos | 10 (561 insertions, 37 deletions) |

## Archivos exactos (10)

```
.env.example
compose.yaml
docs/phases/16c/commit-candidate-010.md
docs/phases/16c/deployment-apply-plan-0.2.0.md
src/application/services/backfill.py
src/application/services/certification_snapshot.py
src/interfaces/cli/paper_runner.py
tests/test_backfill.py
tests/test_certification_snapshot.py
tests/test_cli_paper_runner.py
```

## Diff stat

```
 .env.example                                       |   4 +-
 compose.yaml                                       |   6 +-
 docs/phases/16c/commit-candidate-010.md            | 172 +++++++++++++++++++++
 docs/phases/16c/deployment-apply-plan-0.2.0.md     | 148 +++++++++++++++---
 src/application/services/backfill.py               |  12 +-
 src/application/services/certification_snapshot.py |  15 ++
 src/interfaces/cli/paper_runner.py                 |  42 ++++-
 tests/test_backfill.py                             |  48 +++++-
 tests/test_certification_snapshot.py               |  10 ++
 tests/test_cli_paper_runner.py                     | 141 +++++++++++++++++
 10 files changed, 561 insertions(+), 37 deletions(-)
```

## Invariantes verificados (item 1)

| Invariante | Evidencia |
|---|---|
| fresh session: `last is None` ⇒ sin fetch REST, 0 events, 0 candles, `recovered=0` | `test_fresh_session_never_fetches_history` PASS |
| existing session: recovery desde `last + interval` | `test_existing_session_backfills_only_from_last_plus_interval`, `test_backfill_one_lost_candle` PASS |
| START NOT_STARTED/INVALIDATED exige sesión prístina | `test_operator_start_rejected_with_prior_events/_prior_candles` PASS |
| reject ⇒ sin anchor | mismas pruebas (no se crea/**.json**, estado intacto) |
| RUNNING second START ⇒ no-op | `test_operator_start_anchors_and_is_idempotent` PASS |
| restart conserva anchor | `test_restart_recompose_preserves_anchor`, `test_operator_start_restart_preserves_identity_and_anchor` PASS |
| INVALIDATED exige sesión limpia | `test_invalidated_recertification_requires_fresh_session` PASS |
| predicado puro | `test_pristine_session_conflict` PASS |

**11/11 invariantes PASS.**

## SESSION SWITCH (item 2) — corregido antes del commit

El plan (Paso 14/15) se corrigió: la sesión de certificación **se persiste en `.env`**
(`PAPER_SESSION_ID=paper-certification-…`) **antes** del one-shot, de modo que el one-shot y el
servicio normal resuelven al **mismo** `session_id`. No se pasa `--session-id` solo al one-shot.
Invariante documentado en §8 del `deployment-apply-plan-0.2.0.md`.

## Gates (item 3)

| Gate | Resultado |
|---|---|
| focused unit | **115 passed** |
| recovery E2E | **10 passed** |
| certification E2E | **9 passed** |
| full product suite + coverage | **727 passed, 1 skipped · 93.66%** (≥90%) |
| harness suite + coverage | **91 passed · 80.25%** (≥80%) |
| ruff check/format (root) | **PASS** (268 formatted) |
| ruff (harness) | **PASS** (24 files) |
| mypy | **Success: 235 files** |
| strict JSON | **PASS** (E2E case8) |
| `git diff --cached --check` | **PASS** (sin exclusiones) |
| secret scan | **NO_SECRETS** |

## Post-commit

| Check | Resultado |
|---|---|
| `git show --stat --oneline HEAD` | 10 files, +561/−37 |
| `git diff HEAD^ HEAD --check` | **PASS** |
| `git status --short` | **vacío** (working tree limpio) |

## codebase-memory-mcp post-commit (§4.13)

| Paso | Resultado |
|---|---|
| re-index (`index_repository`, moderate) | 3096 nodos / 14447 edges · 0 skipped/parse_partial |
| `detect_changes` since `47acd2e` (both) | 10 changed_files · 14 seed_symbols · **104 impacted** (transitivo) |
| `check_index_coverage` (archivos tocados) | `no_recorded_issue` en `src/**`, tests, `compose.yaml`, `.env.example`; `docs/` excluido por diseño |

Blast radius: 0 cambios en `src/domain` (matemática de trading/risk intacta). El impacto transitivo
(104) corresponde a callers/callees del wiring (`_run`, `_run_loop`, `certification_snapshot`) y a
los fakes de test.

## Estado de certificación

- **Paper sigue NO CERTIFIED.**
- `FINAL_DEPLOY_SHA` (`47acd2e…`) permanece como base; el fix se integra vía PR futuro hacia
  `feature/phase-08-llm-decision-agent`. El nuevo SHA tras el merge será el `GIT_COMMIT` de deployment.

## Artefacto post-commit

- `docs/phases/16c/post-commit-verification-009.md` (este archivo) queda **sin trackear**.

## NO ejecutado (requiere GATE explícito posterior)

- `git push` · PR · merge
- modificar lenovosrv · migración productiva · redeploy
- Prometheus/Grafana productivos · safeguard drills · START Certification
- tag/release · live trading

---

**Resultado: POST_COMMIT_PASS** — 16c.8 integrado en `9ae8859`. Paper sigue **NO certificado**.
Siguiente: `READY_FOR_EVIDENCE_COMMIT_GATE` (commit de este reporte) y, después, push/PR.

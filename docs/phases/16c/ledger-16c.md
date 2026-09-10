# Ledger — Fase 16c · Paper Certification (schema v2 / restart-safe) · 0.2.0

> Fuente de verdad del cierre 16c: este ledger complementa al ledger del plan SDD
> (`.superpowers/sdd/2026-09-09-paper-certification-state-v2-producer-16c6/progress.md`),
> que registra por-Task el detalle de fixes y minors deferred.
> La certificación oficial del Paper sigue viviendo en el ledger `harness/state` y en los
> gates del arnés; este documento es el estado de avance del cierre 16c.

## Estado por sub-entregable

| Sub-entregable | Estado | Comentario |
|---|---|---|
| 16c.1 · Recovery | **COMPLETE** | `restore_runner`/replay determinista restart-safe; gap/divergencia ⇒ STOP. Commit `0350839`. |
| 16c.2 · Decision evidence | **COMPLETE** | `decision_context` JSONB + recompute no-lookahead. Commit `1b62354`. |
| 16c.3 · Persistent observability | **COMPLETE** | Logging JSON estructurado + config Prometheus. Commit `49bcefd`. |
| 16c.4 · Certification Gate | **COMPLETE** | Evaluador determinista operacional (13 checks, sin promedio/compensación), 30d reales UTC, freeze 10 campos, JSON machine-readable. Commit `66448dc`. |
| 16c.5a · D3 idempotency | **COMPLETE** | Dedup de velas ya procesadas antes de mutar estado (crash-after-commit = no-op). Commit `6eac3c7`. |
| 16c.5 · Integrated recovery E2E | **COMPLETE** | E2E integrada recovery/auditabilidad E2E-1..10 (`NO_RESTART_TRACE == RESTART_TRACE`). Commit `9065563`. |
| 16c.6 · Integrated Certification State v2 & Release Closure | **READY_FOR_COMMIT_GATE** | Producer v2 real (frozen/current/operational) crash-safe, reloj explícito NOT_STARTED→START, identidad al START, reconciliación three-way con checkpoint (F1/F2), preservación del `frozen` anclado ante mismatch de identidad (Task 8d punto 1 + 4 regresiones), safeguard drills, E2E productor→evaluador, bump 0.2.0. Gates verdes (719 passed / 93.69% producto · 91 / 80.25% arnés · E2E 9 · ruff/mypy limpios · secretos 0 · Alembic single-head 0011). `commit-candidate-007.md` → **READY_FOR_USER_GATE**. Sin commit. |

## Gates 16c.6 — FINAL post-Task 8d (re-ejecutados contra el árbol final)

> Artefactos y cifras refrescados en `docs/phases/16c/evidence/` (sustituyen a las pasadas
> pre-F1/F2 y pre-8d). Detalle en `evidence/log.md`.

| Gate | Resultado |
|---|---|
| Full producto + cobertura | **719 passed, 1 skipped** · 93.69% branch (≥90) |
| Arnés + cobertura | **91 passed** · 80.25% branch (≥80) |
| E2E productor→estado→evaluador | **9 passed** (incl. caso 9 mid-run fills, strict JSON caso 8) |
| Ruff check / format | All checks passed / 268 files already formatted |
| Mypy | Success: no issues in 235 source files |
| Secret scan | **0** sobre los 35 archivos tocados |
| Version consistency | 3 passed (`0.2.0` runtime == pyproject) |
| Cadena Alembic | single head `0011_paper_events_context`; upgrade head + downgrade −1 OK en DB descartable (pasada previa, migraciones sin cambios); productiva **MANUAL post-GATE** |

## Paper Certification

**Paper NO está marcado como certificado.** El bump a `0.2.0` invalida por diseño cualquier
certificación `0.1.x` previa; certificar una sesión real requiere redeploy integrado y una
nueva sesión de ≥ 30 días evaluada con el gate determinista — decisión de despliegue posterior
al GATE del usuario, fuera de este cierre de código.

## Carry-over post-merge (prohibido editar a mano)

`python3 harness/scripts/progress.py report` muestra la Fase 16 como `in_progress` con
`1/5 done · 4 bloqueados · 20% · gate pending`: el `add-phase` del tronco
(`feature/phase-08-llm-decision-agent`, `3e8d15f`) **no** incluye aún los sub-entregables 16c
en `harness/state/progress.yaml`.

- El alta de entregables 16c en `progress.yaml` (vía `harness/scripts/progress.py add-phase`
  / `mark-done` con su evidencia) queda como **carry-over post-merge** de esta rama a `main`.
- **Prohibido editar `harness/state/progress.yaml` a mano** (AGENTS.md §9): el ledger oficial
  lo calcula `progress.py` sobre entregables con evidencia.

## Post-commit (16c.6)

| Campo | Valor |
|---|---|
| commit | `adc88cd0db39d5ded209497a0b0d6464e2a78f7f` — `feat(phase-16c): producer schema v2 restart-safe + bump 0.2.0 (cierre integrado)` |
| estado | **POST_COMMIT_PASS** (16c.6 integrado) |
| verificación | `git status --short` vacío · `git diff HEAD^ HEAD --check` OK · re-index 3087 nodos/14440 edges (0 skipped/0 parse_partial) · `detect_changes since 66448dc` 35/286/54 (0 en `src/domain`) · cobertura `no_recorded_issue` |
| arnés | `progress.py`: Fase 16 `1/5` (4 bloqueados = certificación real pendiente) · `gate_check --phase 16`: 4 PASS · 1 FAIL (`scope-complete`, esperado) · 2 MANUAL |
| **Paper** | **NO certificado** (la sesión real de ≥30 días sigue pendiente) |
| reporte | `docs/phases/16c/post-commit-verification-007.md` |
| NO ejecutado | push · merge · tag · redeploy · migración productiva · inicio de Paper Certification |

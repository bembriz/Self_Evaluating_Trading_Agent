# Commit Candidate Report — 2026-09-12 (Fase 17G)

> NO staging / NO commit / NO push ejecutados. Solo preparación.

## Objetivo

Máquina mínima de promoción hasta HOLDOUT_READY (MVP-A): promueve por
evidencia, rechaza STABLE_NEGATIVE, bloquea estados post-MVP-A, no consume
el holdout.

## Rama / Base

| Campo | Valor |
|---|---|
| branch | feature/phase-08-llm-decision-agent (pre-existente) |
| base commit | 91174bf |

## Archivos

- **Creados:**
  - `src/lab/promote.py` (~330 líneas: máquina + persistencia file-first)
  - `tests/lab/test_promote.py` (31 tests: 13 gates + matrices de rechazo + determinismo)
  - `docs/phases/17G/evidence/` (promotion.md, baseline-promotion/,
    logs: promote-tests, lab-tests, integration-tests, coverage-global,
    coverage-17g-modules, lint, lint-repo, format, mypy, mypy-repo, log.md,
    baseline-evaluation)
  - `docs/phases/17G/commit-candidate-001.md` (este archivo)
- **Modificados / eliminados:** ninguno.

## Arquitectura afectada

Solo `src/lab/` (nuevo, aislado). Sin cambios a `registry.py` (no extendido).
Runtime protegido intacto; sin seam nuevo.

## Índice del grafo

- [ ] Re-indexar tras el commit — pendiente hasta APPROVED
- [ ] `check_index_coverage` — pendiente hasta APPROVED

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| tests/lab | 256 passed | evidence/lab-tests.log |
| tests/integration | 15 passed | evidence/integration-tests.log |
| Global `--cov=src --cov-branch --cov-fail-under=90` | 696 passed · 95.82% | evidence/coverage-global.log |
| `promote.py` statements/branches | 100% / 100% | evidence/coverage-17g-modules.log |

## Calidad

```bash
uv run ruff check src/ tests/   # All checks passed!
uv run ruff format --check ...  # PASS
uv run mypy src tests           # Success, 222 files
```

## Seguridad / Safety

- [x] Sin secretos · [x] HOLDOUT PRISTINE · [x] Cero lecturas del holdout
- [x] Baseline evaluado: PARITY_PASSED, HOLDOUT_READY=NO

## Riesgos / Deuda

Riesgo mínimo (módulo nuevo sin consumidores en producción). Sin deuda nueva.

## Mensaje de commit propuesto

```
feat(lab): add evidence-gated promotion state machine (17G)
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

# Commit Candidate Report — 2026-09-12 (Fase 17E)

> NO staging / NO commit / NO push ejecutados. Solo preparación.

## Objetivo

ExperimentRegistry filesystem mínimo + verificación double-run de
reproducibilidad (Mode 2). Sin DB/ORM, sin promotion logic, sin
walk-forward orchestration, sin holdout.

## Rama / Base

| Campo | Valor |
|---|---|
| branch | feature/phase-08-llm-decision-agent (pre-existente) |
| base commit | 6411d34 |

## Archivos

- **Creados:**
  - `src/lab/registry.py` (~230 líneas: registry + `compare_runs`)
  - `tests/lab/test_registry.py` (15 tests: gates 1–12 + idempotencia run + secuencias anidadas)
  - `docs/phases/17E/evidence/` (reproducibility.md, double-run/registry + reproducibility.json, logs: registry-tests, lab-tests, integration-tests, coverage-global, coverage-17e-modules, lint, lint-repo, format, mypy, mypy-repo, log.md, double-run)
  - `docs/phases/17E/commit-candidate-001.md` (este archivo)
- **Modificados:** ninguno. **Eliminados:** ninguno.

## Arquitectura afectada

Solo `src/lab/` (nuevo, aislado). Blast radius nulo: runtime protegido
intacto (`git diff 6411d34` vacío en las 7 rutas). No se necesitó seam nuevo.

## Índice del grafo

- [ ] Re-indexar tras el commit (`index_repository`) — pendiente hasta APPROVED
- [ ] `check_index_coverage` sobre archivos tocados — pendiente hasta APPROVED

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| tests/lab | 199 passed | evidence/lab-tests.log |
| tests/integration | 15 passed | evidence/integration-tests.log |
| Global `--cov=src --cov-branch --cov-fail-under=90` | 639 passed, 1 skipped · 95.62% | evidence/coverage-global.log |
| registry.py statements/branches | 100% / 100% | evidence/coverage-17e-modules.log |

## Calidad

```bash
uv run ruff check src/ tests/   # All checks passed!
uv run ruff format --check ...  # PASS
uv run mypy src tests           # Success, 216 files
```

## Seguridad / Safety

- [x] Sin secretos en el diff · [x] HOLDOUT PRISTINE · [x] Sin acceso a FINAL_HOLDOUT
- [x] `application_git_sha` solo como provenance (run 17e-double-run-a/b)

## Riesgos / Deuda

Riesgo mínimo (módulo nuevo sin consumidores en producción). Sin deuda nueva.

## Mensaje de commit propuesto

```
feat(lab): add filesystem experiment registry and double-run check (17E)
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

# Commit Candidate Report — 2026-09-12 (Fase 17F)

> NO staging / NO commit / NO push ejecutados. Solo preparación.

## Objetivo

Walk-forward MVP + robustez básica con runtimes existentes. Resultado válido:
edge negativo estable (sin EDGE_PRESENT, sin promotion gate).

## Rama / Base

| Campo | Valor |
|---|---|
| branch | feature/phase-08-llm-decision-agent (pre-existente) |
| base commit | c8f34e1 |

## Archivos

- **Creados:**
  - `src/lab/walk_forward.py` (ventanas, reconstrucción de trades, métricas, agregado)
  - `src/lab/robustness.py` (7 variantes explícitas + `summarize_robustness`)
  - `tests/lab/test_walkforward.py` (17 tests: gates 1–10 + geometría + agregado)
  - `tests/lab/test_robustness.py` (9 tests: set, mapeo, reglas, wiring real)
  - `docs/phases/17F/evidence/` (walkforward-robustness.md, walkforward.json,
    robustness.json, registry/ con 10 specs + 11 runs, logs: wf-tests,
    lab-tests, integration-tests, coverage-global, coverage-17f-modules,
    lint, lint-repo, format, mypy, mypy-repo, log.md, walkforward-evidence)
  - `docs/phases/17F/commit-candidate-001.md` (este archivo)
- **Modificados / eliminados:** ninguno.

## Arquitectura afectada

Solo `src/lab/` (nuevo, aislado). Métricas reutilizadas de
`domain.evaluation.metrics` (cero fórmulas duplicadas). Runtime protegido
intacto; no se necesitó seam nuevo.

## Índice del grafo

- [ ] Re-indexar tras el commit — pendiente hasta APPROVED
- [ ] `check_index_coverage` — pendiente hasta APPROVED

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| tests/lab | 225 passed | evidence/lab-tests.log |
| tests/integration | 15 passed | evidence/integration-tests.log |
| Global `--cov=src --cov-branch --cov-fail-under=90` | 665 passed · 95.67% | evidence/coverage-global.log |
| `walk_forward.py` + `robustness.py` | 100% stmts / 100% branch | evidence/coverage-17f-modules.log |

## Calidad

```bash
uv run ruff check src/ tests/   # All checks passed!
uv run ruff format --check ...  # PASS
uv run mypy src tests           # Success, 220 files
```

## Seguridad / Safety

- [x] Sin secretos · [x] HOLDOUT PRISTINE · [x] FINAL_HOLDOUT solo bloqueado
- [x] Sin minería de parámetros (sin selección/promoción en el código)

## Riesgos / Deuda

Riesgo mínimo (módulos nuevos sin consumidores en producción). Sin deuda nueva.

## Mensaje de commit propuesto

```
feat(lab): add walk-forward and robustness evaluation (17F)
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

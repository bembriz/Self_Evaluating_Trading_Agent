# Commit Candidate Report — 2026-09-11 (Fase 17D)

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> NO staging / NO commit / NO push ejecutados. Solo preparación.

## Objetivo

Mode 2 — Runtime Parity para Strategy Lab: `FrozenDatasetAdapter` (lectura
validada del dataset congelado, holdout denegado) + `LabSessionRunner`
(estrategia real + PaperEngine real sobre velas congeladas, timing MVP-A).
Sin segundo motor, sin reglas duplicadas, sin tocar runtime certificado.

## Rama

| Campo | Valor |
|---|---|
| branch | feature/phase-08-llm-decision-agent (pre-existente) |
| base commit | 96998e6 |

## Archivos

- **Creados:**
  - `src/lab/frozen_dataset.py` (~190 líneas)
  - `src/lab/session_runner.py` (~170 líneas)
  - `tests/lab/test_frozen_dataset.py` (21 tests)
  - `tests/lab/test_session_runner.py` (8 tests: paridad ×3, determinismo ×2, experimento, smoke DEV real, spec-id inválido)
  - `docs/phases/17D/evidence/` (parity.md + logs: lab-tests, paper-risk-tests, coverage-global, lint, lint-repo, format, mypy, mypy-repo, log.md)
  - `docs/phases/17D/commit-candidate-001.md` (este archivo)
- **Modificados:** ninguno
- **Eliminados:** ninguno

## Diff

```bash
git status --short -- src/lab/frozen_dataset.py src/lab/session_runner.py \
  tests/lab/test_frozen_dataset.py tests/lab/test_session_runner.py docs/phases/17D/
# 5 rutas ??, solo creaciones; `git diff 96998e6 --stat -- src/` → solo los 2 módulos nuevos
```

## Arquitectura afectada

Solo `src/lab/` (nuevo, aislado: importado únicamente por los tests nuevos).
Blast radius: nulo sobre runtime — `paper_runner`, `paper_engine`,
`domain/risk/`, `domain/portfolio/`, `domain/trading/strategy.py`,
`infrastructure/bybit/`, `interfaces/cli/paper_runner.py` intactos
(`git diff 96998e6 -- <protegidos>` vacío). No se necesitó seam nuevo:
NO aplica NEEDS_POST_CERTIFICATION_CHANGE.

## Índice del grafo

- [ ] Índice re-indexado tras el commit (`index_repository`) — pendiente hasta APPROVED
- [ ] Cobertura verificada sobre archivos tocados (`check_index_coverage`) — pendiente hasta APPROVED

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| tests/lab (regresión 17A–C + 29 nuevos) | 184 passed | docs/phases/17D/evidence/lab-tests.log |
| Paper/Risk/Strategy/Portfolio (8 suites) | 82 passed | docs/phases/17D/evidence/paper-risk-tests.log |
| Global `--cov=src --cov-branch --cov-fail-under=90` | 622 passed, 1 skipped, 2 failed* | docs/phases/17D/evidence/coverage-full.log |

\* 2 failed = `tests/integration/test_memory_repository.py` (PREEXISTING_FAILURE:
pgvector exige 384 dims, el test inserta 4 dims; sin relación con 17D).
Verificado con PostgreSQL disponible; 0 errores.

## Cobertura

95.38% global (branch), umbral 90% alcanzado. Módulos nuevos 17D: 100% statements, 100% branches.

## Calidad

```bash
uv run ruff check src/ tests/       # All checks passed!
uv run ruff format --check <4 archivos>  # PASS
uv run mypy src tests               # Success, 214 files
```

## Seguridad

- [x] Sin secretos en el diff (código + JSON de estado + logs de test)
- [x] Sin archivos .env ni credenciales
- [x] Holdout intacto: `holdout/v1.state.json` = PRISTINE (sin rutas de escritura nuevas)

## Riesgos

Bajo. Dos módulos nuevos sin consumidores en producción; el runner es
single-use y determinista. Riesgo principal: rama actual no específica de 17D.

## Deuda técnica

Ninguna nueva. Registry/promotion/walk-forward orchestration quedan para
fases posteriores según spec (no creados, como exige 17D).

## Mensaje de commit propuesto

```
feat(lab): add Mode 2 runtime parity adapter and session runner (17D)

- src/lab/frozen_dataset.py: validated frozen-dataset reads, holdout denied
- src/lab/session_runner.py: real strategy + real PaperEngine over frozen candles
- tests/lab/test_frozen_dataset.py + test_session_runner.py: 29 tests
  (holdout safety incl. ramas defensivas 100%, determinism, experiment linkage,
  cross-harness parity)
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

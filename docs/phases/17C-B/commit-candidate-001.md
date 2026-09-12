# Commit Candidate Report — 2026-09-11 (Fase 17C-B)

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> NO staging / NO commit / NO push ejecutados. Solo preparación.

## Objetivo

Congelar formalmente el Split v1 (fronteras aprobadas por
HUMAN_SPLIT_FREEZE_GATE, idénticas a la propuesta 17C-A), crear el estado
inicial PRISTINE del holdout y agregar el guard mínimo `is_holdout_range`.

## Rama

| Campo | Valor |
|---|---|
| branch | feature/phase-08-llm-decision-agent (pre-existente, no creada en 17C-B) |
| base commit | fc1aaba |

## Archivos

- **Creados:**
  - `src/lab/splits.py` (40 líneas: constantes v1 + `is_holdout_range`)
  - `splits/v1.json` (split_version=1 + human_approval)
  - `holdout/v1.state.json` (PRISTINE)
  - `tests/lab/test_splits.py` (158 líneas, 26 tests)
  - `docs/phases/17C-B/evidence/` (freeze.md + logs: splits-tests, coverage-global, lint, lint-repo, format, format-repo, mypy, mypy-repo, log.md)
  - `docs/phases/17C-B/commit-candidate-001.md` (este archivo)
- **Modificados:**
  - `tests/test_split_candidate_17c_a.py` (solo anotaciones de tipado para el gate mypy repo-wide; sin cambios de comportamiento ni fronteras)
- **Eliminados:** ninguno

Nota de alcance: `splits/CANDIDATE.json` y `docs/phases/17C-A/` pertenecen al
alcance 17C-A (candidato separado, ya validado); no se incluyen aquí salvo el
retoque de tipado citado arriba, requerido por el gate `mypy src tests`.

## Diff

```bash
git status --short -- src/lab/splits.py splits/v1.json holdout/v1.state.json \
  tests/lab/test_splits.py tests/test_split_candidate_17c_a.py docs/phases/17C-B/
# 7 rutas ??/M, todas listadas arriba; ver `git diff` (untracked: `git diff --no-index /dev/null <file>`)
```

## Arquitectura afectada

`src/lab/` (dominio experimental) + artefactos de datos versionados
(`splits/`, `holdout/`). Blast radius: `src/lab/splits.py` es nuevo y aislado
(ningún módulo existente lo importa — verificado por grep). Sin cambios en
runtime certificado: paper_runner, paper_engine, risk, portfolio, strategy.

## Índice del grafo

- [ ] Índice re-indexado tras el commit (`index_repository`) — pendiente hasta APPROVED
- [ ] Cobertura verificada sobre archivos tocados (`check_index_coverage`) — pendiente hasta APPROVED

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| 17C-B + lab + 17C-A (`tests/lab/test_splits.py`, `tests/lab/`, `tests/test_split_candidate_17c_a.py`) | 166 passed | docs/phases/17C-B/evidence/splits-tests.log |
| Global `--cov=src --cov-branch --cov-fail-under=90` | 580 passed, 1 skipped, 15 errors* | docs/phases/17C-B/evidence/coverage-global.log |

\* 15 errors = `tests/integration/*` por PostgreSQL no disponible en el entorno
(connection refused 127.0.0.1:5433); 0 errores fuera de integration.

## Cobertura

93.71% global (branch), umbral 90% alcanzado.

## Calidad

```bash
uv run ruff check src/ tests/       # resultado: All checks passed!
uv run ruff format --check <3 archivos tocados>  # resultado: PASS
uv run mypy src tests               # resultado: Success, 210 files checked
uv run pytest --cov=src --cov-branch --cov-fail-under=90  # 580 passed (ver nota DB)
```

## Seguridad

- [x] Sin secretos en el diff (solo rangos, timestamps, JSON de estado y código del guard)
- [x] Sin archivos .env ni credenciales
- [x] Secret scanning N/A (sin credenciales en el alcance)

## Riesgos

Bajo. Archivos nuevos + 1 test tocado (tipado). `splits/v1.json` y
`holdout/v1.state.json` son datos congelados; el guard falla cerrado. Riesgo
principal: rama actual (`feature/phase-08-llm-decision-agent`) no es específica
de 17C-B — el humano decide si commitear aquí o mover a rama dedicada.

## Deuda técnica

Ninguna nueva. `splits/CANDIDATE.json` (17C-A) sigue sin commitear; coordinar
con su candidato. Los 15 errors de integration requieren Postgres en CI/entorno.

## Mensaje de commit propuesto

```
feat(lab): freeze split v1 and pristine holdout state (17C-B)

- splits/v1.json: DEVELOPMENT [0,62208), WALK_FORWARD [62208,88128),
  FINAL_HOLDOUT [88128,103680) + HUMAN_SPLIT_FREEZE_GATE approval
- holdout/v1.state.json: PRISTINE initial state
- src/lab/splits.py: is_holdout_range guard (fail-closed)
- tests/lab/test_splits.py: 26 tests (geometry, determinism, guard, state)
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

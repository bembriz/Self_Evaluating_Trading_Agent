# Commit Candidate Report — 2026-09-09 · 16c.6 CI hardening (Draft PR #1)

> Obligatorio antes de `git commit` (PRD §65-66). Estado: **READY_FOR_USER_GATE**
> (autorizado por el usuario para commit + push al head del Draft PR #1).

## Objetivo

Endurecer CI antes de marcar el Draft PR #1 como Ready for Review:

1. Que CI corra en PRs hacia **cualquier** rama (`pull_request:` sin filtro de rama),
   sin hardcodear `feature/phase-08-llm-decision-agent`.
2. Añadir job **harness** (uv sync --frozen + pytest con cobertura ≥80 % del arnés).
3. Añadir job **diff-check** con alcance que excluya únicamente los logs de evidencia
   históricos, y confirme PASS en el resto del rango del PR. No se modifican logs
   históricos por trailing whitespace.

## Rama / base

| Campo | Valor |
|---|---|
| branch | `fix/phase-16c-restart-safe` |
| base del PR | `feature/phase-08-llm-decision-agent` (`74bbf2f`) |
| head (antes de este commit) | `538f7b1` |
| Draft PR | #1 (https://github.com/bembriz/Self_Evaluating_Trading_Agent/pull/1) |

## Archivos

- **Modificado:** `.github/workflows/ci.yml`
  - `on:` → `push: branches:[main]` + `pull_request:` (sin filtro).
  - Nuevo job `harness` (working-directory `harness`, `uv sync --frozen`,
    `uv run pytest --cov=scripts --cov-branch --cov-fail-under=80`).
  - Nuevo job `diff-check` (checkout fetch-depth 0; calcula BASE/HEAD desde el evento
    PR o push; `git diff --check BASE...HEAD` con `:(exclude,glob)docs/phases/16/evidence/*.log`
    y `:(exclude)docs/phases/16/evidence/log.md`).
- **Creado:** `docs/phases/16c/commit-candidate-008.md` (este reporte).
- **Creado:** `docs/phases/16c/evidence/ci-hardening-scoped-diffcheck-16c6.log`.
- **Modificado:** `docs/phases/16c/evidence/log.md` (línea de evidencia del cambio).

## Diff

```text
.github/workflows/ci.yml                          | ~30 +++++-
docs/phases/16c/commit-candidate-008.md           | nuevo
docs/phases/16c/evidence/ci-hardening-scoped-diffcheck-16c6.log | nuevo
docs/phases/16c/evidence/log.md                   | 1 +
```

## Hallazgo / decisión

`git diff --check` del rango `74bbf2f...538f7b1` reporta trailing whitespace **solo** en
logs de evidencia históricos bajo `docs/phases/16/evidence/`: 9 archivos `*.log` **y**
`log.md`. El glob pedido `docs/phases/16/evidence/*.log` no cubre `log.md`; para lograr
PASS sin modificar logs históricos, el job excluye ambos (`*.log` + `log.md`). No hay
trailing whitespace fuera de `docs/phases/16/evidence/`.

## Verificación

| Gate | Resultado |
|---|---|
| YAML válido | PASS (jobs: quality, integration, security, docker, harness, diff-check) |
| scoped diff-check (local, `74bbf2f...538f7b1`, excl. evidence logs) | **PASS** |
| diff-check sin exclusión (control) | falla solo en evidence logs (esperado) |
| quality local (ruff check / ruff format --check / mypy src tests) | PASS (268 files / 235 files) |
| harness local (`uv sync --frozen` + pytest cov ≥80) | PASS · 80.25 % |
| integration / security / docker | **pendientes de GitHub Actions** (se ejecutarán al push) |

## Riesgos

- CI real (integration con Postgres+pgvector, gitleaks, docker build) se valida en Actions
  tras el push; si falla, se reportará sin auto-fix.
- El job `diff-check` usa `github.event.pull_request.base.sha`/`head.sha` (PR) o
  `before`/`sha` (push); con `fetch-depth: 0` el rango es resoluble.

## Deuda / notas

- No se modifican logs históricos (solo exclusión en el check).
- Sin cambios de código de producto/tests.

## Mensaje de commit propuesto

```
ci(phase-16c): run CI on all PRs + harness job + scoped diff-check

- ci.yml: pull_request sin filtro de rama (no hardcodea la rama base del PR)
- nuevo job harness: uv sync --frozen + pytest --cov=scripts --cov-fail-under=80
- nuevo job diff-check scoped: git diff --check con exclusión de logs de evidencia
  históricos (docs/phases/16/evidence/*.log + log.md); PASS en el resto del rango
- evidencia + commit candidate del cambio CI
- sin cambios de producto/tests; Paper sigue NOT CERTIFIED
```

**estado: READY_FOR_USER_GATE**

# Commit Candidate 001 — Fase 17A (Strategy Lab: ExperimentSpec/Run)

> Preparado para HUMAN 17A GATE. NO commit / NO push / NO deploy hasta aprobación.

## Objetivo

Implementar Fase 17A del plan `implementation-plan-1b-strategy-lab.md`:
`ExperimentSpec`/`ExperimentRun`, serialización canónica, `ExperimentSpecId`,
`EventTraceHash`, `MetricsHash`. TDD RED→GREEN; goldens verificados por vía
independiente (`sha256sum`); reproducibilidad en segundo proceso probada en-suite.

## Rama

`feature/phase-08-llm-decision-agent` (rama de trabajo actual; la fase 17A vive aquí
hasta decisión del gate sobre su destino de merge).

## Archivos (solo creados; 0 modificados)

- `src/lab/__init__.py` (nuevo, docstring)
- `src/lab/experiment_spec.py` (nuevo, ~230 líneas: contrato CANONICAL_JSON v1,
  `ExperimentSpec`, `ExperimentRun`, hashes)
- `tests/lab/test_experiment_spec.py` (nuevo, 77 tests)
- `docs/phases/17A/evidence/` (unit-tests.log, coverage.json, global-coverage.log,
  lint.log, format.log, typing.log, log.md)

## Diff summary

- `git status`: únicamente `?? src/lab/`, `?? tests/lab/`, `?? docs/phases/17A/`.
- `git diff --stat` sobre boundary protegido
  (`paper_runner.py`, `paper_engine.py`, `cli/paper_runner.py`, `domain/risk/`,
  `domain/portfolio/`, `infrastructure/bybit/`, `domain/trading/strategy.py`):
  **vacío**. Los 3 ficheros tracked modificados visibles en `git status`
  (`docs/phases/16/evidence/log.md`, `harness/state/progress.yaml`, `opencode.json`)
  son preexistentes (mtime 2026-09-06, anteriores a esta fase).

## Tests

- `tests/lab/test_experiment_spec.py`: **77 passed** (incl. 21-param mutación
  semántica, 12 casos canónicos fail-closed, goldens, subprocess 2º proceso).
- Suite ejecutable (`tests --ignore=tests/integration --ignore=tests/e2e`):
  **491 passed, 1 skipped**. Integración/e2e excluidas: requieren PostgreSQL
  (`localhost:5433`, `Connection refused` local; causa ambiental preexistente,
  ver `global-coverage.log`).

## Cobertura exacta

- `src/lab/experiment_spec.py`: **100% stmts + 100% branches**
  (`src/lab/__init__.py`: 0 stmts, 100%).
- Global (set ejecutable): **93.08% ≥ 90%** (`TOTAL 4150 stmts`).
  Faltantes restantes en paths cubiertos por integración en CI (mains CLI, etc.).

## Calidad

- `ruff check src/lab tests/lab`: PASS. `ruff format --check`: PASS.
- `mypy src/lab tests/lab` (strict): PASS, 3 archivos sin issues.

## Seguridad

- Sin secretos, sin red, sin I/O fuera de `hashlib`/`json` stdlib; 0 dependencias
  nuevas (stdlib + dataclasses). `pyproject.toml` NO tocado (nota: `src/lab` aún no
  está en `packages` de hatchling — follow-up consciente de empaquetado para 17B+,
  sin efecto en tests/CI actual).

## Riesgos

- Bajo. Módulo puro sin consumidores todavía (17B+ lo usará). Superficie: hashing
  y validación de formatos. Goldens fijan el contrato contra regresiones
  silenciosas.

## Deuda / follow-ups

1. Incluir `src/lab` en `packages` de hatchling al cerrar MVP-A (empaquetado wheel).
2. 17B definirá el contenido de `kernel_identity` (hoy placeholder opaco).
3. Integración/e2e pendientes de entorno con PG (ajeno a esta fase).

## Mensaje propuesto

```
feat(lab-17a): ExperimentSpec/Run + canonical hashing + SpecId

Fase 17A del Strategy Lab (plan implementation-plan-1b). Contrato
CANONICAL_JSON v1, ExperimentSpecId determinista (solo inputs semánticos;
provenance en ExperimentRun), EventTraceHash/MetricsHash. TDD 77 tests,
goldens verificados vía sha256sum independiente, reproducibilidad en
segundo proceso. Cobertura nuevo módulo 100%, global 93.08%. Sin cambios
al runtime protegido. Sin commit/push/deploy hasta HUMAN 17A GATE.
```

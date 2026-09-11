# Commit Candidate 002 — Fase 17A: fixes del HUMAN CODE REVIEW

> Supersede a `commit-candidate-001.md` (mismo scope, +2 blockers corregidos).
> NO commit / NO push / NO deploy hasta aprobación. NO 17B.

## Blockers del human review y fixes

### BLOCKER 1 — Deep immutability (RESUELTO)

- Problema: `ExperimentSpec(frozen=True)` con mappings/listas internos mutables;
  `spec.dataset["id"] = "OTHER"` habría cambiado el SpecId.
- Fix (`src/lab/experiment_spec.py`): normalizar primero y después deep-freeze
  recursivo — `dict → MappingProxyType`, `list → tuple` (nuevo `_freeze()`,
  aplicado en `_section()` a las 8 secciones incl. `walk_forward`).
  `canonical_json` serializa los congelados vía su normalización (Mapping y
  tuple ya aceptados) con JSON idéntico.
- Goldens: **PERMANECEN EXACTAMENTE IGUALES** (`f5e4a00f…`, `b4643e9d…`,
  `783829de…`, `03dd7b93…` — los 4 tests golden en verde sin tocar literales),
  porque la representación JSON semántica no cambió. No hubo STOP que declarar.
- Tests nuevos (6): mutación top-level rechazada; mutación anidada rechazada;
  mutación de lista (`[0]=` TypeError, `.append` AttributeError); mutación del
  input caller post-construcción no altera el Spec (containers + SpecId);
  SpecId estable tras intentos; tipos congelados (`MappingProxyType`/`tuple`).

### BLOCKER 2 — Enum ordering (RESUELTO)

- Problema: `_normalize` aceptaba str/int antes de rechazar Enum; `StrEnum`
  (es str) e `IntEnum` (es int) atravesaban el fail-closed.
- Fix: chequeo `isinstance(value, Enum)` movido ANTES de la aceptación
  str/bool/int, sin conversión a `.value`. Docstring actualizado.
- Tests nuevos: `StrEnum` y `IntEnum` rechazados con TypeError (con asserts
  previos de que efectivamente son instancias str/int — el test fallaría
  vacuamente si no lo fueran).

### Mejora — provenance con SpecId real

- Nuevo test: dos `ExperimentRun` sobre `sid = spec_id(spec_real)` con
  provenance totalmente distinta (run_id, created_at, git_sha, hashes)
  apuntan al mismo `sid`. Tests anteriores de separación se conservan.

## Archivos (solo creados/modificados en scope)

- `src/lab/__init__.py` (sin cambios desde 001)
- `src/lab/experiment_spec.py` (fix: `_freeze`, orden Enum, docstring)
- `tests/lab/test_experiment_spec.py` (86 tests: 77 + 9 nuevos/entonces +
  ajustes; ver detalle abajo)
- `docs/phases/17A/evidence/` (re-evidenciado completo)
- `docs/phases/17A/commit-candidate-002.md` (este archivo)

Conteo de tests nuevos netos: +2 enum, +6 inmutabilidad, +1 provenance real = 9
(77 → 86).

## Tests

- `tests/lab/test_experiment_spec.py`: **86 passed** (incl. goldens sin tocar,
  subprocess 2º proceso).
- Suite ejecutable (`--ignore=tests/integration --ignore=tests/e2e`):
  **500 passed, 1 skipped** (integración/e2e excluidas: sin PostgreSQL local,
  `Connection refused`; causa ambiental preexistente).

## Cobertura exacta

- `src/lab/experiment_spec.py`: **100% stmts, 100% branches** (133 stmts/56 ramas).
- Global (set ejecutable): **93.09% ≥ 90%**.

## Calidad

- `ruff check`: PASS. `ruff format --check`: PASS. `mypy --strict`: PASS.

## Exact changeset

- Untracked 17A: `?? src/lab/`, `?? tests/lab/`, `?? docs/phases/17A/`.
- `git diff --stat` sobre boundary protegido (`paper_runner.py`, `paper_engine.py`,
  `cli/paper_runner.py`, `domain/risk/`, `domain/portfolio/`,
  `infrastructure/bybit/`, `domain/trading/strategy.py`): **vacío**.
- Los 3 tracked modificados (`docs/phases/16/evidence/log.md`,
  `harness/state/progress.yaml`, `opencode.json`) son PREEXISTENTES
  (mtime 2026-09-06) y NO se incorporan.

## Seguridad

- Sin secretos/red/I-O; 0 dependencias nuevas; stdlib (`types.MappingProxyType`
  añadido a imports). `pyproject.toml` intacto.

## Riesgos

- Bajo. Cambio confinado a `src/lab/` sin consumidores. `MappingProxyType` es
  read-only estándar; la única semántica nueva es rechazo donde antes había
  mutabilidad silenciosa (el comportamiento deseado del blocker).

## Mensaje propuesto

```
feat(lab): add deterministic experiment identity
```

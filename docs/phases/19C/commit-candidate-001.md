# Commit Candidate Report — 2026-09-13

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> Preparado para el gate de implementación 19C (enforcement fix). Nada está
> staged ni commiteado.

## Objetivo

Convertir el guard pre-WALK_FORWARD de Phase 19C en un **choke point mecánico
real**: `FrozenDatasetAdapter` deniega por defecto cualquier rango que
interseque WALK_FORWARD, y la única ruta que puede abrirlo es
`guarded_walk_forward_open` tras resultado `IMPROVED`, viabilidad absoluta PASS y
autorización humana explícita. Sin nuevos estados ni framework.

## Rama

| Campo | Valor |
|---|---|
| branch | `feature/phase-08-llm-decision-agent` |
| base commit | `7ea8b2c7ce74b02bdd539f1b04ee2fc9ede6564f` (19B committed) |
| staging | none (`git diff --cached --exit-code` PASS) |

## Archivos

- **Modificados (Lab):**
  - `src/lab/frozen_dataset.py` — boundary de acceso (deny WF por defecto,
    validador pre-IO, opener privado autorizado).
  - `tests/conftest.py` — fixture `synthetic_frozen_repo` (repo sintético).
  - `tests/lab/test_frozen_dataset.py` — tests de boundary.
  - `tests/lab/test_walkforward.py` — acceso WF vía guard.
  - `tests/e2e/test_strategy_lab_e2e.py` — ventanas WF vía guard.
- **Creados (producción):** `src/lab/viability.py`.
- **Creados (tooling):** `harness/scripts/phase19c_viability_evidence.py`.
- **Creados (tests):** `tests/lab/test_viability.py`.
- **Creados (diseño):** `docs/superpowers/specs/2026-09-12-absolute-viability-gate-design.md`.
- **Creados (evidencia):** `docs/phases/19C/`.
- **Eliminados:** `tests/lab/conftest.py` (consolidado en `tests/conftest.py`).

No se modifica `src/lab/promote.py`, `ParityEvidence`, `LabSessionRunner`, ni el
runtime protegido.

## Enforcement (arquitectura)

- `FrozenDatasetAdapter.from_repo(...)` y `FrozenDatasetAdapter(...)` públicos
  aplican `_validate_range` **antes de cualquier IO de dataset**:
  - DEVELOPMENT → permitido;
  - cualquier rango que intersecte `[62208, 88128)` → **DENEGADO** (mensaje que
    indica usar `guarded_walk_forward_open`);
  - cualquier rango que intersecte FINAL_HOLDOUT → denegado siempre.
- Ruta interna privada `FrozenDatasetAdapter._from_repo_authorized_walk_forward`
  autorizada por token de módulo; **único caller de producción/lab**:
  `guarded_walk_forward_open`.
- `guarded_walk_forward_open` ordena: (1) `DEVELOPMENT_RESULT == IMPROVED`,
  (2) `AbsoluteViabilityEvidence.passed`, (3) `human_authorized`, y solo entonces
  (4) invoca el opener autorizado → (5) IO de dataset. La ruta autorizada sigue
  bloqueando FINAL_HOLDOUT.
- `lab.walk_forward.walk_forward_windows` sigue siendo solo productor de rangos;
  no se le añadió política. `LabSessionRunner` sin cambios.

## Truth table — Absolute Viability

| net_pnl | expectancy | profit_factor | passed |
|---|---|---|---|
| 1.0 | 0.5 | 1.5 | true |
| 0.0 | 0.5 | 1.5 | false |
| 1.0 | 0.0 | 1.5 | false |
| 1.0 | 0.5 | 1.0 | false |
| -1.0 | 0.5 | 1.5 | false |
| None | 0.5 | 1.5 | false |
| NaN | 0.5 | 1.5 | false |
| +inf | 0.5 | 1.5 | false |
| -inf | 0.5 | 1.5 | false |
| 1.0 | 0.5 | +inf | false |

## Truth table — Elegibilidad

| development_result | viability | eligible |
|---|---|---|
| IMPROVED | PASS | true |
| IMPROVED | FAIL | false |
| MIXED | PASS | false |
| MIXED | FAIL | false |
| NOT_IMPROVED | PASS | false |
| NOT_IMPROVED | FAIL | false |

## Auditoría de bypass (read-only)

- `PUBLIC_WALK_FORWARD_ACCESS=DENIED` (sin construcción pública en `src/`).
- `AUTHORIZED_WALK_FORWARD_PATHS=1`; caller único:
  `guarded_walk_forward_open`.
- `GUARD_BEFORE_ADAPTER_CREATION=YES`, `GUARD_BEFORE_DATASET_IO=YES`.
- `WALK_FORWARD_GUARD_BYPASS_FOUND=NO`; `BYPASS_PATHS=NONE`.
- `INELIGIBLE_ADAPTER_CREATIONS=0`, `INELIGIBLE_WALK_FORWARD_READS=0`.
- Evidencia: `docs/phases/19C/evidence/bypass-audit.log`.

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Lab | 390 passed | `docs/phases/19C/evidence/tests-lab.log` |
| Integration | 43 passed | `docs/phases/19C/evidence/tests-integration.log` |
| E2E | 16 passed | `docs/phases/19C/evidence/tests-e2e.log` |
| Global | 883 passed, 1 skipped | `docs/phases/19C/evidence/coverage-global.log` |

Cubierto: deny público WF (from_repo y `__init__`) antes de IO; deny de rangos de
`walk_forward_windows`; acceso autorizado con fixture sintético; holdout
inaccesible incluso por la ruta autorizada; truth tables de viabilidad y
elegibilidad; `PARITY_PASSED` + viability FAIL coexisten; sin estados nuevos;
cero creaciones de adapter y cero lecturas en candidatos no elegibles.

## Cobertura

- Global combined statement/branch: `96.21%` (umbral 90% superado).
- `src/lab/viability.py`: `100%` statements y branches.
- `src/lab/frozen_dataset.py` (modificado): `100%` statements y branches.
- Evidencia: `docs/phases/19C/evidence/coverage.json` y `coverage-19c.json`.

## Calidad

```bash
uv run ruff check .          # PASS - docs/phases/19C/evidence/ruff.log
uv run ruff format --check . # PASS - docs/phases/19C/evidence/format.log
uv run mypy src tests        # PASS - docs/phases/19C/evidence/mypy.log
uv run pytest --cov=src      # 883 passed, 1 skipped, 96.21% - coverage-global.log
```

## Data safety (test data isolation)

- Tests de enforcement/autorización y los tests 17F/17H convertidos usan el repo
  **sintético** (`synthetic_frozen_repo`): `ROUTINE_TEST_REAL_WALK_FORWARD_READS=0`
  y `PHASE_19C_REAL_WALK_FORWARD_READS=0`.
- Legacy real-WF tests convertidos a sintético (2):
  - `tests/lab/test_walkforward.py::test_windows_temporal_order_on_real_data`
    → `test_windows_temporal_order_on_synthetic_authorized_data`;
  - `tests/e2e/test_strategy_lab_e2e.py::test_e2e_strategy_lab_full_chain`
    (ventanas WF sobre repo sintético; aserciones estructurales preservadas).
- Solo cambia la fuente de datos; las aserciones originales se mantienen.
- El hecho histórico de que 17F consumió WALK_FORWARD legítimamente se preserva
  (`HISTORICAL_WALK_FORWARD_CONSUMPTION=YES`); no se reescribe evidencia, métrica,
  registry ni SpecId histórico.
- `FINAL_HOLDOUT_READS=0`, `FINAL_HOLDOUT_EXECUTIONS=0`, `HOLDOUT_STATE=PRISTINE`
  (`docs/phases/19C/evidence/holdout-state.log`).
- No se ejecuta WALK_FORWARD ni evaluación económica.

## Inmutabilidad histórica

- `docs/phases/18B`, `docs/phases/18D`, `docs/phases/19B` sin cambios
  (`historical-immutability.log` exit 0).
- 17G `promote.py` / `ParityEvidence` sin cambios; estados sin cambios.
- Runtime protegido intacto (`protected-runtime-diff.log` exit 0).

## Riesgos

- El token de capacidad es privado de módulo (no un control criptográfico); un
  caller podría importarlo. La auditoría estática confirma que no existe en
  producción/lab fuera del opener.
- `profit_factor == inf` falla cerrado por diseño.

## Deuda técnica

- No hay todavía un orquestador de walk-forward en producción; el choke point
  queda listo para que el futuro harness lo use.

## Mensaje de commit propuesto

```text
feat(lab): enforce walk-forward access boundary with viability guard (19C)

- deny WALK_FORWARD by default in FrozenDatasetAdapter (public API, pre-IO)
- add private authorized opener used only by guarded_walk_forward_open
- add absolute viability gate, eligibility guard, tests and evidence
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

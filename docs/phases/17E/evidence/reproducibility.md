# FASE 17E — ExperimentRegistry + Double-Run Reproducibility

> Filesystem-only, sin DB/ORM, sin promotion logic, sin walk-forward
> orchestration, sin holdout. Reutiliza ExperimentSpec/Run,
> StrategyArtifactIdentity, KernelIdentity sin cambiar su semántica.

- Base: `6411d34` (sin modificar implementación).
- Nuevo: `src/lab/registry.py` — `ExperimentRegistry` (`<root>/<spec_id>/spec.json`,
  `runs/<run_id>.json`), idempotente ante contenido idéntico, fail closed
  (`SpecConflictError`/`RunConflictError`) ante contenido conflictivo,
  verificación anti-manipulación en carga, `list_runs` para auditoría;
  `compare_runs` → `ReproducibilityReport`.
- Double-run (DEVELOPMENT [0,64), EmaRsiBaseline + PaperEngine reales,
  identidades reales): SPEC_ID `ae0e88be…499f`, hashes idénticos,
  RunIds distintos → REPRODUCIBLE=YES (ver `double-run/reproducibility.json`
  y `double-run/registry/`).

## Calidad (evidencia en este directorio)

| Check | Resultado |
|---|---|
| tests/lab (199: regresión + 15 nuevos 17E) | 199 passed |
| tests/integration (PostgreSQL) | 15 passed |
| global `--cov=src --cov-branch --cov-fail-under=90` | 639 passed, 1 skipped · **95.62%** ✔ |
| `src/lab/registry.py` | 100% statements, 100% branches ✔ |
| `ruff check src/ tests/` · `ruff format --check` · `mypy src tests` (216) | PASS / PASS / PASS |

## Safety

`holdout/v1.state.json` = PRISTINE (el registry/tests no tienen rutas de
escritura fuera de su root); runtime protegido CLEAN
(`git diff 6411d34 -- <7 rutas protegidas>` vacío).

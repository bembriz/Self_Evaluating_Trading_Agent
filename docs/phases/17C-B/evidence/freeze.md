# FASE 17C-B — Freeze Split v1 + Holdout PRISTINE

> HUMAN_SPLIT_FREEZE_GATE=APPROVED. Fronteras copiadas exactas de la propuesta
> 17C-A, sin cambios. Sin estrategias, sin backtest, sin replay, sin métricas
> sobre FINAL_HOLDOUT.

- Base: `fc1aaba` + trabajo 17C-A (CANDIDATE.json verificado, sin modificar salvo
  anotaciones de tipado en su test — ver nota abajo).
- Dataset: `BYBIT_ETHBTC_V001` (ETHUSDT 15m, 103680 filas).
- Manifest SHA: `3c008c3ab5299e33beaa61c80ddc927d2f14fc3f96924b5d6db537b2a4e91644`

## Rangos congelados ([start, end))

| Split | Rango | Rows | Primero | Último |
|---|---|---|---|---|
| DEVELOPMENT | [0, 62208) | 62208 | 2023-09-08T17:45:00+00:00 | 2025-06-17T17:30:00+00:00 |
| WALK_FORWARD | [62208, 88128) | 25920 | 2025-06-17T17:45:00+00:00 | 2026-03-14T17:30:00+00:00 |
| FINAL_HOLDOUT | [88128, 103680) | 15552 | 2026-03-14T17:45:00+00:00 | 2026-08-23T17:30:00+00:00 |

- Artefactos: `splits/v1.json` (con `human_approval.reason=HUMAN_SPLIT_FREEZE_GATE`),
  `holdout/v1.state.json` (`holdout_id=BYBIT_ETHBTC_V001-holdout-v1`, `state=PRISTINE`).
- Guard: `src/lab/splits.py::is_holdout_range(start, end)` → True si [start,end)
  intersecta [88128, 103680); ValueError (fail closed) en rangos inválidos.

## Validaciones

- TOTAL 103680 = 62208+25920+88128 ✔ · NO_OVERLAP=YES · NO_GAPS=YES ·
  TEMPORAL_ORDER=YES · holdout termina en la última fila ✔
- `splits/v1.json` reproducible desde CANDIDATE.json salvo `approved_at` ✔
- `tests/lab/test_splits.py`: 26 tests (guard: dev/wf/pre-holdout permitidos,
  dentro/cruce rechazados, inválidos con ValueError; v1==candidate; PRISTINE) ✔

## Calidad (evidencia en este directorio)

| Check | Resultado |
|---|---|
| targeted tests (tests/lab + 17C-A) | 166 passed |
| global `pytest --cov=src --cov-branch --cov-fail-under=90` | 580 passed, 1 skipped, 15 errors* · coverage **93.71%** ✔ |
| `ruff check src/ tests/` | PASS |
| `ruff format --check` (archivos tocados) | PASS |
| `mypy src tests` (210 files) | PASS |

\* Los 15 errors son `tests/integration/*` por PostgreSQL no disponible
(`connection refused 127.0.0.1:5433`); cero errores fuera de integration.
Pre-existente y ambiental, sin relación con 17C-B.

Nota: para el gate mypy repo-wide se agregaron anotaciones de tipado
(`-> None`, `dict[str, Any]`) a `tests/test_split_candidate_17c_a.py` (17C-A).
Solo tests, sin cambio de comportamiento ni de fronteras.

## Runtime protegido

`git diff fc1aaba -- src/` contiene únicamente `src/lab/splits.py` (nuevo,
aislado: ningún otro módulo lo importa) → CLEAN (paper_runner, paper_engine,
risk, portfolio, strategy intactos).

# FASE 17G — Promotion State Machine MVP-A (evidencia por encima de fases)

> 17F_IMPLEMENTATION=PASS (infraestructura) pero baseline-v1 con
> EDGE_PRESENT=NO y BASELINE_PROMOTABLE=NO no promociona: la máquina evalúa
> EVIDENCIA. STABLE_NEGATIVE es rechazo, no promoción automática.

- Nuevo: `src/lab/promote.py` — estados DRAFT → PARITY_PASSED →
  ROBUSTNESS_PASSED → HOLDOUT_READY; HOLDOUT_PASSED/RELEASE_CANDIDATE/
  PAPER_APPROVED rechazados explícitamente (MVP-B); persistencia file-first
  `promotions/<identity>.state.json` con hash de integridad, historial
  append-only, manipulación fail-closed; research notes sin cambio de estado.
- Baseline real (identidades reales, valores 17F): DRAFT → PARITY_PASSED →
  REJECTED `NEGATIVE_WALK_FORWARD: STABLE_NEGATIVE is rejection` →
  final PARITY_PASSED, HOLDOUT_READY=NO, holdout intacto
  (ver `baseline-promotion/baseline-promotion.json`).
- HOLDOUT_READY exige spec/identidades/kernel/split=1/PRISTINE + aprobación
  humana explícita, y NO consume el holdout.

## Calidad (evidencia en este directorio)

| Check | Resultado |
|---|---|
| tests/lab (256) | 256 passed |
| tests/integration | 15 passed |
| global `--cov=src --cov-branch --cov-fail-under=90` | 696 passed · **95.82%** ✔ |
| `src/lab/promote.py` | 100% statements, 100% branches ✔ |
| `ruff check` / `format --check` / `mypy src tests` (222) | PASS / PASS / PASS |

## Safety

HOLDOUT PRISTINE (cero lecturas del holdout en 17G); runtime protegido
CLEAN; sin criptografía nueva (hash/canonical existentes).

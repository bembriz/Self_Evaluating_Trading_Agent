# UAT — Fase 17H · Strategy Lab MVP-A (humano en el loop)

UAT_STATUS=PASS
UAT_PASSED=10
UAT_FAILED=0
HUMAN_APPROVED=YES
UAT_DATE=2026-09-12

> No marcar PASS automáticamente. La persona ejecuta cada caso, compara con
> el resultado esperado y registra PASS/FAIL + fecha + observaciones.
> Solo lectura del dataset congelado; ningún caso toca FINAL_HOLDOUT para
> analizarlo (UAT-09 verifica únicamente su bloqueo).

## Prerequisitos

- Repo en `43ecf5c` (o posterior 17H) con `.venv` listo (`uv sync`).
- Dataset presente: `datasets/BYBIT_ETHBTC_V001/ETHUSDT_15m.csv`.
- PostgreSQL de test disponible SOLO para UAT de integración
  (opcional; los casos 01–08 y 10 no lo requieren).

## UAT-01 — Dataset / split v1

Comando:

```bash
python3 -c "import json; c=json.load(open('splits/v1.json')); print(c['dataset_id'], c['total_rows'], [(s['name'],s['row_start'],s['row_end']) for s in c['splits']])"
```

Revisar: `BYBIT_ETHBTC_V001 103680`, DEVELOPMENT `[0,62208)`,
WALK_FORWARD `[62208,88128)`, FINAL_HOLDOUT `[88128,103680)`.
Esperado: esos valores exactos. PASS/FAIL: PASS Fecha: 2026-09-12

## UAT-02 — Experimento permitido en DEVELOPMENT

Comando:

```bash
uv run pytest tests/e2e/test_strategy_lab_e2e.py::test_e2e_strategy_lab_full_chain -q --no-cov
```

Revisar: salida `1 passed`. Esperado: PASS sin errores. PASS/FAIL: PASS Fecha: 2026-09-12

## UAT-03 — SpecId / RunId

Comando:

```bash
python3 -c "import json; e=json.load(open('docs/phases/17E/evidence/double-run/reproducibility.json')); print(e['SPEC_ID'], e['RUN_A_ID'], e['RUN_B_ID'])"
```

Revisar: SPEC_ID de 64 hex iguales en ambas corridas; RunIds distintos
(`17e-double-run-a` vs `17e-double-run-b`). PASS/FAIL: PASS Fecha: 2026-09-12

## UAT-04 — Registry persistido

Comando:

```bash
ls docs/phases/17E/evidence/double-run/registry/*/spec.json docs/phases/17E/evidence/double-run/registry/*/runs/*.json
```

Revisar: existe `spec.json` + 2 runs bajo el mismo SpecId.
PASS/FAIL: PASS Fecha: 2026-09-12

## UAT-05 — Double-run representativo

Comando:

```bash
python3 -c "import json; e=json.load(open('docs/phases/17E/evidence/double-run/reproducibility.json')); print(e['EVENT_TRACE_HASH_MATCH'], e['METRICS_HASH_MATCH'], e['REPRODUCIBLE'])"
```

Esperado: `YES YES YES`. PASS/FAIL: PASS Fecha: 2026-09-12

## UAT-06 — Walk-forward

Comando:

```bash
python3 -c "import json; w=json.load(open('docs/phases/17F/evidence/walkforward.json')); print(w['aggregate']['total_windows'], w['aggregate']['profitable_windows'], w['aggregate']['losing_windows'], round(w['aggregate']['aggregate_net_pnl'],4))"
```

Esperado: `3 0 3 -16.0739` (0/3 rentables = resultado válido, no fallo).
PASS/FAIL: PASS Fecha: 2026-09-12

## UAT-07 — Robustness

Comando:

```bash
python3 -c "import json; r=json.load(open('docs/phases/17F/evidence/robustness.json')); print(r['summary']['variants'], r['summary']['stable'])"
```

Esperado: `7 YES` (YES = negativo-estable, NO significa rentable).
PASS/FAIL: PASS Fecha: 2026-09-12

## UAT-08 — Rechazo del baseline

Comando:

```bash
python3 -c "import json; e=json.load(open('docs/phases/17G/evidence/baseline-promotion/baseline-promotion.json')); print(e['BASELINE_PROMOTION_STATE'], e['BASELINE_ROBUSTNESS_PROMOTION'][:8], e['BASELINE_HOLDOUT_READY'])"
```

Esperado: `PARITY_PASSED REJECTED NO`.
PASS/FAIL: PASS Fecha: 2026-09-12

## UAT-09 — Acceso a FINAL_HOLDOUT bloqueado

Comando:

```bash
uv run python -c "from lab.frozen_dataset import FrozenDatasetAdapter; from pathlib import Path; FrozenDatasetAdapter.from_repo(Path('.'), symbol='ETHUSDT', timeframe='15m', row_start=88128, row_end=88129)"
```

Esperado: termina con `ValueError: range intersects FINAL_HOLDOUT`
(código de salida ≠ 0). No se lee ni analiza el holdout.
PASS/FAIL: PASS Fecha: 2026-09-12

## UAT-10 — HOLDOUT_STATE=PRISTINE

Comando:

```bash
python3 -c "import json; print(json.load(open('holdout/v1.state.json')))"
```

Esperado: `{'holdout_id': 'BYBIT_ETHBTC_V001-holdout-v1', 'split_version': 1, 'state': 'PRISTINE'}`.
PASS/FAIL: PASS Fecha: 2026-09-12

## Veredicto global

UAT_STATUS final: APPROVED · Fecha: 2026-09-12 · Firma: humano (sesión UAT facilitada)

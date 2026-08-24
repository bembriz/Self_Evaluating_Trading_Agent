# UAT — Fase 07: ML Baseline

> Prueba de aceptación de usuario (HITL). El agente NO puede aprobar UAT.
> Ejecuta los pasos tal cual y completa "Resultado observado" y el veredicto final.

## Precondiciones

| # | Precondición | Verificada ☐ |
|---|---|---|
| 1 | Entorno `uv` operativo (`.venv` presente) | |
| 2 | `uv run pytest` verde antes de empezar | |

## Pasos

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | `uv run pytest tests/test_logistic_regression.py tests/test_ml_features.py tests/test_walk_forward.py tests/test_experiment.py tests/test_ml_pipeline.py tests/test_ml_no_lookahead.py -q` | 29 tests PASS |
| 2 | `uv run pytest --cov=src --cov-branch --cov-fail-under=90 -q` | 206 passed · cobertura 96.46% |
| 3 | Ejecutar el snippet de demostración (abajo) | Imprime experiment_id, trades y métricas de clasificación, sin errores |
| 4 | `uv run ruff check . && uv run mypy src tests` | `All checks passed!` y `Success: no issues found` |

## Snippet de demostración (Paso 3)

```bash
uv run python -c "
from application.services.ml_pipeline import MlBaselineConfig, run_ml_baseline
from domain.market.candle import Candle

candles = []
prev = 100.0
for i in range(2000):
    close = prev * (1.0 + 0.0004 + (0.004 if i % 40 < 20 else -0.004))
    candles.append(Candle(i*3600_000, prev, max(prev, close), min(prev, close), close, 1.0, close))
    prev = close

r = run_ml_baseline(candles, MlBaselineConfig(initial_train=400, val_size=200, step=200))
print('experiment_id =', r.experiment_id)
print('trades =', r.metrics.trades, '· net_pnl =', round(r.metrics.net_pnl, 2))
print('accuracy =', round(r.classification.accuracy, 3), '· n =', r.classification.n)
"
```

## Evidencia a adjuntar

Salida del Paso 3 (experiment_id/trades/net_pnl/accuracy) y el resumen de pytest de los Pasos 1–2.

## Resultado observado

| Paso | Resultado observado | ¿Coincide? (SÍ/NO) | Notas |
|---|---|---|---|
| 1 | 29 tests PASS | SÍ | |
| 2 | 206 passed · 96.46% | SÍ | |
| 3 | experiment_id=22d15ec638088cee · trades=35 · net_pnl=776.84 · accuracy=0.65 | SÍ | |
| 4 | All checks passed · Success: no issues | SÍ | |

## Incidencias encontradas

Ninguna.

---

## VEREDICTO UAT: APPROVED
Decisor: usuario  Fecha: 2026-08-23
Comentario: UAT ejecutado por el usuario; resultados coinciden. Aprobación explícita vía OpenCode.

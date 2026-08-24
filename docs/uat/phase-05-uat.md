# UAT — Fase 05: Feature Engine & Market State

> Prueba de aceptación de usuario (HITL). El agente NO puede aprobar UAT.
> Ejecuta los pasos tal cual y completa "Resultado observado" y el veredicto final.

## Precondiciones

| # | Precondición | Verificada ☐ |
|---|---|---|
| 1 | Entorno `uv` operativo (`.venv` presente) | |
| 2 | `uv run pytest` verde antes de empezar | |

## Entradas / Datos

- Suite de tests: `tests/test_indicators.py`, `tests/test_regime.py`, `tests/test_feature_engine.py`, `tests/test_no_lookahead.py`.
- Snippet de demostración (ver Paso 3).

## Pasos

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | `uv run pytest tests/test_indicators.py tests/test_regime.py tests/test_feature_engine.py tests/test_no_lookahead.py -q` | 36 tests PASS (11+11+8+7 sin error) |
| 2 | `uv run pytest --cov=src --cov-branch --cov-fail-under=90 -q` | 128 passed; cobertura ≥90% (≈94.84%) |
| 3 | Ejecutar el snippet de demostración (abajo) | Imprime un `MarketState` con regime=`trend_up`/`trend_down`, features multi-timeframe y BTC context, sin errores |
| 4 | `uv run ruff check . && uv run mypy src tests` | `All checks passed!` y `Success: no issues found` |

## Snippet de demostración (Paso 3)

```bash
uv run python -c "
from domain.market.candle import Candle, Timeframe
from domain.market.feature_engine import FeatureEngine
from domain.market.orderbook import MarketDataHealth

def series(n, start=100.0, step=0.002):
    out, prev = [], start
    for i in range(n):
        c = prev * (1 + step)
        out.append(Candle(i*3600_000, prev, c+5, prev-5, c, 1.0, c))
        prev = c
    return out

s = FeatureEngine().compute_state('ETHUSDT', MarketDataHealth.HEALTHY,
    {Timeframe.M15: series(300), Timeframe.H1: series(150), Timeframe.H4: series(60)},
    btc_candles=series(150, start=30000.0))
print('regime  =', s.regime)
print('ts      =', s.timestamp_ms)
print('h1 rsi  =', round(s.timeframes[Timeframe.H1].rsi, 2))
print('btc rsi =', round(s.btc.rsi, 2))
"
```

## Evidencia a adjuntar

Salida del Paso 3 (regime, ts, rsi) y el resumen de pytest de los Pasos 1–2.

## Resultado observado

| Paso | Resultado observado | ¿Coincide? (SÍ/NO) | Notas |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |

## Incidencias encontradas

> Desviaciones, errores o comportamientos inesperados.

---

## VEREDICTO UAT: PENDING
<!-- Sustituir PENDING por APPROVED o REJECTED. gate_check exige el veredicto APPROVED visible (los comentarios HTML no cuentan) al check uat-approved -->
Decisor: ________________  Fecha: ________
Comentario:

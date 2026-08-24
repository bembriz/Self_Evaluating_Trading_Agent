# UAT — Fase 06: Backtesting & Deterministic Baseline

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
| 1 | `uv run pytest tests/test_costs_fill.py tests/test_portfolio.py tests/test_metrics.py tests/test_strategy.py tests/test_backtest_engine.py tests/test_backtest_no_lookahead.py tests/test_buy_hold.py -q` | 49 tests PASS |
| 2 | `uv run pytest --cov=src --cov-branch --cov-fail-under=90 -q` | 177 passed · cobertura 96.03% |
| 3 | Ejecutar el snippet de demostración (abajo) | Imprime un `BacktestResult` con trades/métricas y la comparativa Buy & Hold, sin errores |
| 4 | `uv run ruff check . && uv run mypy src tests` | `All checks passed!` y `Success: no issues found` |

## Snippet de demostración (Paso 3)

```bash
uv run python -c "
from application.services.backtest_engine import BacktestEngine
from domain.evaluation.buy_hold import run_buy_and_hold
from domain.market.candle import Candle
from domain.trading.strategy import EmaRsiBaseline

candles = []
prev = 100.0
for i in range(5000):
    close = prev * (1.0 + 0.0002 + (0.002 if i % 50 < 25 else -0.002))
    candles.append(Candle(i*3600_000, prev, max(prev, close), min(prev, close), close, 1.0, close))
    prev = close

result = BacktestEngine(EmaRsiBaseline()).run(candles)
m = result.metrics
print('signals =', result.signals, '· trades =', m.trades)
print('net_pnl =', round(m.net_pnl, 2), '· fees =', round(m.fees, 2), '· slippage =', round(m.slippage, 2))
print('win_rate =', None if m.win_rate is None else round(m.win_rate, 3), '· max_dd =', round(m.max_drawdown, 3))

bh = run_buy_and_hold(candles)
print('Buy & Hold net_pnl =', round(bh.net_pnl, 2))
"
```

## Evidencia a adjuntar

Salida del Paso 3 (signals/trades/net_pnl/fees/slippage/B&H) y el resumen de pytest de los Pasos 1–2.

## Resultado observado

| Paso | Resultado observado | ¿Coincide? (SÍ/NO) | Notas |
|---|---|---|---|
| 1 | 49 tests PASS (suite de la fase) | SÍ | |
| 2 | 177 passed · 96.03% | SÍ | |
| 3 | signals=1089 · trades=99 · net_pnl=823.32 · fees=275.62 · slippage=55.12 · Buy&Hold=1683.79 | SÍ | |
| 4 | All checks passed · Success: no issues | SÍ | |

## Incidencias encontradas

Errores de shell al pegar comandos multi-línea (artefacto de copy-paste), no fallos de la suite.

---

## VEREDICTO UAT: APPROVED
Decisor: usuario  Fecha: 2026-08-23
Comentario: Demo y resultados coinciden; aprobación explícita del usuario vía OpenCode.

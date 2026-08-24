# ADR-0003 — Motor de backtest determinista con ejecución al open de la vela siguiente

**Fecha:** 2026-08-23
**Estado:** accepted

## Contexto

La Fase 06 exige un motor de backtesting event-driven determinista (PRD §25), un baseline de reglas versionado (PRD §29), contabilidad de portfolio exacta y métricas completas (PRD §45). La skill `data-leakage` (PRD §34) prohíbe usar información futura; el clásico error es "decidir con el close de la vela actual y ejecutar en esa misma vela".

## Decisión

1. **Ejecución al open de la vela siguiente**: la señal generada al cierre de la vela `i` se ejecuta al open de la vela `i+1`. La señal de la última vela nunca se ejecuta. Esto elimina el lookahead de forma estructural y verificable.
2. **Motor puro y determinista**: iteración estrictamente ordenada por `timestamp_ms`, sin aleatoriedad, sin I/O. Re-corrida idéntica bit a bit (verificado con test de determinismo).
3. **`float` IEEE-754** para toda la contabilidad (continuación de ADR-0002), con invariantes de negocio explícitos: SELL solo reduce posición (sin short), cash nunca negativo, fees+slippage siempre aplicados. La "exactitud" se entiende como corrección contable (sin short, sin doble conteo), no como precisión infinita.
4. **Baseline versionado `baseline-v1`**: cruce de EMA fast(20)/slow(50) con salida adicional por RSI(14) sobrecomprado (>80). Trackers incrementales con seeds idénticos a `indicators.ema/rsi`, verificados por test de equivalencia incremental-vs-batch.
5. **Métricas en `domain/evaluation/metrics.py`**: las mínimas de PRD §45 (Gross/Net/Fully Loaded PnL, Win/Loss Rate, Profit Factor, Sharpe, Sortino, Max Drawdown, Expectancy, Avg Winner/Loser, Risk/Reward, Fees, Slippage, LLM Cost, Trades, Holding Time, Exposure).

## Alternativas consideradas

| Opción | Consecuencia si se elige |
|---|---|
| Ejecutar al close de la misma vela | Lookahead clásico (PRD §34); requiere justificar que el close es conocido al ejecutar |
| `Decimal` para contabilidad | Mayor fricción (mypy, conversiones, sqrt en métricas) sin cambiar los invariantes de negocio |
| Recomputar EMA/RSI batch en cada vela (O(n²)) | Simple pero ineficiente para 20k+ velas; divergencia si se usa ventana acotada |

## Consecuencias

### Positivas

- No-lookahead garantizado por construcción, testeable con corruptor temporal + replay truncado.
- Determinismo probado (test de dos corridas idénticas).
- Cero dependencias nuevas; módulos críticos (PnL, portfolio, fills, fees, slippage) a 100% branch.

### Negativas / trade-offs aceptados

- La señal de la última vela no se materializa (asume que no hay ejecución instantánea): conservador y aceptable para un baseline.
- `float` sin redondeo monetario: suficiente para backtest; la contabilidad LIVE (Fase 10+) podrá reevaluar `Decimal`.

### Neutras

- Buy & Hold reutiliza `FillModel`/`Portfolio`/`compute_metrics` para comparabilidad directa (PRD §31).

# ADR-0002 — Feature Engine puro en stdlib y régimen determinista versionado

**Fecha:** 2026-08-23
**Estado:** accepted

## Contexto

La Fase 05 exige indicadores técnicos (RSI/MACD/EMA/ATR/VWAP, returns, volatilidad realizada, momentum, volumen relativo), features de order book, contexto BTC, estado multi-timeframe y clasificación de régimen (PRD §15–16). El PRD §15 ordena "implementar internamente siempre que sea razonable" y "no introducir TA-Lib u otra dependencia de indicadores sin justificarla". El proyecto opera bajo control estricto de dependencias (skill `infra-control`, PRD §11) y exige ≥90% cobertura con módulos críticos a 100% branch.

## Decisión

1. **Indicadores en Python stdlib puro** (`math`, `statistics`, `collections.abc`), sin `numpy`/`pandas`/`TA-Lib`. Cada indicador devuelve `list[float | None]` alineado con la entrada, con warmup explícito en `None` y fórmulas causales documentadas (EMA sembrada con SMA, RSI/ATR con suavizado de Wilder).
2. **Régimen determinista y versionado**: `RegimeClassifier.version = "regime-v1"` con `RegimeConfig` frozen (parámetros explícitos). Prioridad: BREAKOUT → volatilidad → tendencia → SIDEWAYS.
3. **Feature Engine como dominio puro** (`domain/market/feature_engine.py`), sin I/O: ensambla un `MarketState` inmutable desde candles por timeframe + snapshot de order book + candles BTC de solo lectura.

## Alternativas consideradas

| Opción | Consecuencia si se elige |
|---|---|
| `numpy`/`pandas` para indicadores | Dependency Proposal + gate obligatorio; mayor superficie de dependencias; performance innecesaria para series pequeñas |
| `TA-Lib` | Prohibido por PRD §15 salvo justificación; requiere binarios nativos |
| Indicadores en `infrastructure` | Rompe la regla hexagonal (dominio debe ser puro y testeable sin I/O) |

## Consecuencias

### Positivas

- Cero dependencias nuevas: no hay Dependency Proposal ni gate adicional para esta fase.
- Dominio 100% puro y determinista: tests unitarios rápidos y reproducibles, sin red ni tiempo real.
- Régimen versionado permite futuros experimentos (PRD §16: "posteriormente podrá evaluarse otro clasificador") sin ambigüedad.
- Warmup explícito (`None`) hace visible y testeable la ausencia de datos suficientes.

### Negativas / trade-offs aceptados

- `float` nativo (IEEE-754) en vez de `decimal`: precisión suficiente para features de decisión; la contabilidad de portfolio (PnL) usará el mecanismo que decida la Fase 06.
- VWAP acumulado "de sesión" sobre la serie recibida: el límite de sesión lo define el llamador; documentado en el docstring.

### Neutras

- Los indicadores operan sobre `Sequence[float]` (series de close) y sobre `Sequence[Candle]` donde se requiere OHLCV (ATR/VWAP/volumen relativo).

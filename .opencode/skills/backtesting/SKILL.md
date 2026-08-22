---
name: backtesting
description: Usar al implementar o ejecutar el motor de backtesting event-driven, market replay determinista, portfolio accounting, fills/fees/slippage, o comparar estrategias sobre el dataset congelado (PRD §25, §29, §40-45)
---

# backtesting — Backtest y replay deterministas

## Propósito

Simulación event-driven reproducible sobre datos congelados: mismo input + misma versión ⇒ mismos números bit a bit. Nunca PnL bruto como métrica: siempre Net/Fully Loaded.

## Cuándo usar

- Fase 06 (motor + baseline determinista) y toda evaluación posterior.
- Validar propuestas del Improvement Engine antes de promoverlas.
- Market replay para depurar decisiones históricas.

**Cuándo NO:** paper trading en vivo (usa Paper Engine de runtime); análisis estadístico post-hoc (validacion-estadistica); diseño de ventanas temporales (walk-forward-validacion).

## Invariantes duras

1. **No lookahead:** la decisión en t solo usa información disponible ≤ t (data-leakage).
2. **Determinismo:** sin aleatoriedad no sembrada; iteración ordenada por (timestamp, secuencia).
3. **Costos siempre:** fees reales Bybit parametrizados + slippage modelado (spread/depth si hay book; modelo conservador si no) + coste LLM cuando aplique.
4. **Dataset congelado:** verificar SHA-256 del manifest ANTES de correr; prohibido modificarlo (PRD §41).
5. **Portfolio accounting exacto:** SELL solo reduce posición existente; balances nunca negativos.

## Componentes

- Event queue temporal → FeatureEngine → Strategy → RiskGate → FillModel(fees, slippage) → Portfolio → Metrics.
- Métricas mínimas PRD §45 (Net PnL, Profit Factor, Sharpe, Sortino, MaxDD, Expectancy...).
- Buy & Hold como benchmark SIEMPRE presente en comparativas.

## Checklist de corrida

1. Hash del dataset verificado + versión anotada en experiment_id.
2. Seeds fijos y registrados (PRD §39).
3. Salida: trades + equity curve + métricas + parámetros exactos persistidos.
4. Re-corrida de humo idéntica ⇒ diff vacío (determinismo probado).
5. Evidencia + registro del experimento.

## Errores comunes

- Usar close de la vela actual para decidir en esa misma vela (lookahead clásico).
- Fees "aproximados" o cero.
- Comparar contra baseline distinto de Buy & Hold sin incluirlo también.

## Referencias

- PRD §25, §27–29, §39–45. Skills: data-leakage, walk-forward-validacion, validacion-estadistica, risk-engine.

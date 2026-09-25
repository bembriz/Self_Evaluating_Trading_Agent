---
name: backtesting
description: Usar al implementar o ejecutar el motor de backtesting event-driven, market replay determinista, portfolio accounting, fills/fees/slippage, comparar estrategias sobre el dataset congelado (PRD §25, §29, §40-45), o al tocar el replay de dos relojes / trade-level execution (velas confirmadas + secuencia de trades, trigger vs fill, fidelidad de ejecución)
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

## Replay de dos relojes (trade-level execution, M7)

Modelo actual de un solo reloj (decisión en close `i`, fill en open `i+1`) **sigue vigente como baseline**; el replay Medallion añade un segundo modelo (ADR-0005) sin reemplazarlo:

- **Reloj de estrategia:** solo velas CONFIRMADAS (15m principal; contexto 1h/4h). Cero velas incompletas.
- **Reloj de ejecución:** secuencia cronológica estricta de trades históricos; la decisión en t se materializa en el **primer trade elegible siguiente** — nunca fill retrospectivo en el close de una vela previa.
- **Con posición abierta:** cada evento evalúa SL/TP/trailing/MFE/MAE y gana el **primer trigger cronológico real** (no a resolución de vela).
- **Trigger ≠ fill:** `*_trigger_timestamp` vs `*_fill_timestamp` y `*_reference_price` vs `*_execution_price` son campos separados e obligatorios; jamás identificarlos en silencio.
- **Fidelidad declarada:** etiqueta `TRADE_SEQUENCE_TAKER_PROXY` (cronología real + slippage/fee existentes; sin claim de cola/spread/book/impacto). Cualquier modelo más fino ⇒ nueva etiqueta + nueva versión.
- **Auditoría trade-a-trade:** contrato completo en `docs/design/medallion-replay-architecture.md` §11; `exit_reason` explícito nunca `UNKNOWN` para trades completados normales.
- **Determinismo:** mismo dataset + misma `execution_model_version` ⇒ mismo hash de traza; versionar cada modelo y comparar modelo viejo vs nuevo, no mezclar resultados.

## Errores comunes

- Usar close de la vela actual para decidir en esa misma vela (lookahead clásico).
- Fees "aproximados" o cero.
- Comparar contra baseline distinto de Buy & Hold sin incluirlo también.
- Evaluar SL/TP/trailing solo al cierre de vela en el replay trade-level (pierde la cronología real y el orden de triggers).
- Silenciar trigger/fill en un solo timestamp "para simplificar".

## Referencias

- PRD §25, §27–29, §39–45. ADR-0003 (un reloj) y ADR-0005 (dos relojes); `docs/design/medallion-replay-architecture.md` §8–§11.
- Skills: data-leakage, walk-forward-validacion, validacion-estadistica, risk-engine, medallion-market-data.

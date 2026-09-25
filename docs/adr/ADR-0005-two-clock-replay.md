# ADR-0005 — Replay de dos relojes: velas confirmadas para estrategia, trades históricos para ejecución

**Fecha:** 2026-09-24
**Estado:** proposed (gate M0)

## Contexto

El replay actual (ADR-0003) decide en el cierre de la vela `i` y ejecuta al open de la vela `i+1`. Ese modelo de un solo reloj es determinista y sin lookahead, pero **no representa la cronología real de ejecución`: dentro de una vela de 15m ocurren miles de trades con orden propio, y SL/TP/trailing/MFE/MAE solo se evalúan a resolución de vela. Los resultados históricos vigentes (fases 21R/22) son evidencia del modelo de ejecución antiguo (§21 del gate M0). Se necesita un replay que use **trades individuales como reloj de ejecución** y **velas confirmadas como reloj de estrategia**, con auditoría trade-a-trade (trigger vs fill, timestamps, exit_reason).

## Decisión

**Dos relojes independientes y estrictamente ordenados:** la estrategia decide solo sobre velas CONFIRMADAS (15m principal; contexto 1h/4h); la ejecución consume la secuencia cronológica de trades públicos ETHUSDT. Una decisión en t se materializa en el primer trade elegible siguiente (nunca retrospectivamente en el close de una vela previa); con posición abierta, cada evento de ejecución evalúa SL/TP/trailing/MFE/MAE y **gana el primer trigger cronológico**. El modelo de ejecución se etiqueta `TRADE_SEQUENCE_TAKER_PROXY` (cronología real + slippage/fee existentes; sin claim de cola/spread/book/impacto). `trigger_timestamp` y `fill_timestamp` son campos separados e obligatorios en el contrato de auditoría (§19–§11 del diseño Medallion).

## Alternativas consideradas

| Opción | Consecuencias si se elige |
|---|---|
| Mantener un solo reloj (velas) con velas más finas (1m) | Reduce pero no elimina la ambigüedad intra-vela; sin cronología de trades reales ni trigger/fill; sigue sin representar fills taker reales |
| Replay de order-book completo (L2/L3) | Fidelidad máxima, pero volumen de datos y complejidad enormes; requiere datasets históricos de book que no se tienen; alcance futuro, no M0–M10 |
| Ejecutar señales al close de la misma vela | Lookahead clásico (prohibido por `data-leakage`) |
| Mezclar: señales en velas, stops evaluados en velas, y "mejorar" fills con trades solo a veces | Fidelidad inconsistente y no auditable; imposible de determinismar por versión de modelo |

## Consecuencias

### Positivas

- Cronología de ejecución mucho más cercana al mercado real; SL/TP/trailing con orden verificable y audits trade-a-trade completos (trigger/fill, MFE/MAE, exit_reason).
- Compatibilidad: el replay de un solo reloj (ADR-0003) **sigue existiendo** como baseline; los dos modelos conviven y se comparan, con `execution_model_version` en cada resultado.
- Determinismo preservado: mismo dataset + misma versión ⇒ mismo hash de traza.

### Negativas / trade-offs aceptados

- `TRADE_SEQUENCE_TAKER_PROXY` no es un fill real: sin cola, spread, profundidad ni impacto (declarado explícitamente, nunca silenciado).
- Coste computacional y de almacenamiento superiores (Bronze/Silver de trades ~2–3 órdenes de magnitud más filas que velas).
- `ORDERING_FIDELITY` puede ser `PARTIAL` cuando el orden nativo no sea demostrable: se declara en Gold en lugar de ocultarlo.

### Neutras

- Kline API de Bybit queda relegada a validación/reconciliación, nunca fuente canónica.
- Las estrategias existentes (Baseline/Donchian/Bollinger) se re-ejecutan en M9 tras validar el nuevo motor; sus resultados vigentes no se reescriben.

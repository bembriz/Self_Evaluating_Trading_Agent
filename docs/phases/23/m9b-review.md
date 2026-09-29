# M9-B Review — Full DEVELOPMENT (OLD close-only vs NEW trade-sequence)

**Fecha:** 2026-09-29 (UTC-6) · **Rama:** `medalion` @ `fcba380e423ee717fe6ffd1244f14ffb072c40b2`
**Método:** revisión **de solo lectura** de los artefactos ya generados en
`/srv/fast/medallion/m9b-full/`. **NO** se ejecutó replay. **NO** se tocó WF/HOLDOUT.
**NO** commit/push/mark-done.

> **Semántica de exit reasons** (no agrupar): `take_profit`=TP · `stop_loss`=SL ·
> `trailing_stop`=categoría **independiente** · `strategy_exit`=salida por señal.
> En OLD el raw `llm_sell` se presenta como `strategy_exit` (mapeo solo de presentación).
> Métrica secundaria permitida: `protective_exits = stop_loss + trailing_stop`.

---

## 1. Inventario de artefactos

Dataset `gold-replay-5ca68f44…` (manifest `c095d574…`, `DEVELOPMENT`), ventana
`[2023-09-09Z, 2025-06-17Z)` = **647 días / 62112 velas 15m**. 6 combinaciones,
cada una con `summary.json` (self-hash) + `trades.jsonl` (ledger, hash en el summary).

| Combinación | closed | TP | SL | trailing | strategy_exit (pres.) | protective = SL+trail | net_pnl | final_equity |
|---|---|---|---|---|---|---|---|---|
| baseline OLD | 631 | 155 | 322 | 62 | 92 (llm_sell) | 384 | −22.812989 | 977.187011 |
| baseline NEW | 631 | 131 | 362 | 78 | 60 | 440 | −24.864136 | 975.135864 |
| donchian OLD | 839 | 199 | 325 | 36 | 279 (llm_sell) | 361 | −27.741589 | 972.258411 |
| donchian NEW | 987 | 215 | 556 | 95 | 121 | 651 | −38.777176 | 961.222824 |
| bollinger OLD | 391 | 2 | 115 | 0 | 274 (llm_sell) | 115 | −16.936591 | 983.063409 |
| bollinger NEW | 405 | 4 | 155 | 0 | 246 | 155 | −18.183960 | 981.816040 |

`rejected decisions = 0` en las 3 corridas NEW (`decisions_rejected=0`, sin motivos).

## 2. Consistencia interna (verificada — `m9b-review-consistency.log`)

Para cada uno de los 6 pares summary+ledger se recomputó desde el ledger y se comparó
con el summary:

- `trade_ledger_records == closed_trades == nº de líneas` del JSONL;
- `trade_ledger_bytes == tamaño` del archivo; `trade_ledger_sha256 == sha256(archivo)`;
- `summary_sha256` auto-consistente (payload sin el propio campo);
- identidad por trade `net_pnl == gross_execution_pnl − fees` (±1e-6); `holding_ms ≥ 0`;
- campos mínimos OLD/NEW y extendidos NEW presentes; `exit_reason_presentation` mapea
  `llm_sell→strategy_exit` y deja el resto intacto;
- timestamps de salida no decrecientes; exit-reason counts raw y de presentación == métricas;
- recomputadas y coincidentes: net, fees, slippage, gross_ref, gross_exec, win_rate,
  expectancy, avg_holding, maxDD abs/pct, final_equity, closed_trades, profit_factor;
- paridad de señales: `signal_hash` y `candle_hash` OLD == NEW en las 3 estrategias.

**Resultado: `ARTIFACTS_INTERNALLY_CONSISTENT=YES`** (0 discrepancias). El smoke de M9-B2B
ya probó determinismo byte-a-byte del runner; aquí se confirma coherencia de los artefactos
reales del Full DEVELOPMENT (no se repitió una corrida completa de 647 días: no aplica).

## 3. Revisión por estrategia

### 3.1 baseline — misma población cerrada, peor economía NEW

| Métrica | OLD | NEW | Δ |
|---|---|---|---|
| closed_trades | 631 | 631 | 0 |
| gross_execution_pnl | 2.434493 | 0.381319 | −2.053174 |
| fees | 25.247482 | 25.245456 | −0.002026 |
| slippage | 5.049497 | 5.049091 | −0.000406 |
| net_pnl | −22.812989 | −24.864136 | −2.051147 |
| expectancy | −0.036154 | −0.039404 | −0.003250 |
| profit_factor | 0.7230 | 0.6242 | −0.0988 |
| win_rate | 0.3043 | 0.2821 | −0.0222 |
| max_drawdown_abs | 26.447965 | 25.389464 | −1.058501 |
| avg_holding_ms | 16 995 879.6 | 11 277 030.1 | −5 718 849.5 |

**Lectura:** el **nº de trades cerrados es idéntico (631)** y la secuencia de señales es la
misma, pero el reloj de ejecución de dos relojes cambia las salidas: más `stop_loss`
(322→362) y menos `take_profit` (155→131); parte de los `llm_sell` de OLD pasan a
`strategy_exit` (60) o a cierres protectores intrabar. El resultado realizado NEW es **peor
por ~2.05** con fees/slippage casi iguales ⇒ la diferencia es de **ejecución/exit path**, no
de costes. Holding medio ~5.7M ms menor en NEW. La igualdad de conteo no implica misma
identidad de trades (entradas/fills distintos).

### 3.2 donchian — cambio importante de población / reentradas

| Métrica | OLD | NEW | Δ |
|---|---|---|---|
| closed_trades | 839 | 987 | **+148 (+17.6 %)** |
| decisiones BUY | 1893 | 2034 | +141 |
| gross_execution_pnl | 5.830954 | 0.711582 | −5.119372 |
| fees | 33.572543 | 39.488758 | +5.916215 |
| slippage | 6.714509 | 7.897752 | +1.183243 |
| net_pnl | −27.741589 | −38.777176 | **−11.035587** |
| expectancy | −0.033065 | −0.039288 | −0.006223 |
| profit_factor | 0.7478 | 0.6573 | −0.0905 |
| win_rate | 0.3027 | 0.2796 | −0.0231 |
| max_drawdown_abs | 29.919263 | 41.969591 | +12.050328 |
| avg_holding_ms | 15 175 566.2 | 10 586 978.5 | −4 588 587.7 |

**Lectura:** la mayor diferencia cualitativa. NEW cierra posiciones antes (protectores
intrabar) y **habilita más reentradas** (BUY 1893→2034; cierres 839→987). Más operaciones ⇒
**más fees (+5.92) y slippage (+1.18)** sobre una base de gross_execution ya pobre ⇒ net
**−11.04** peor y `maxDD` 29.9→42.0. La población NO es comparable (cambia el número y la
cadencia de trades), aunque la señal de decisión (hash) es idéntica.

### 3.3 bollinger — cambio menor pero peor economía NEW

| Métrica | OLD | NEW | Δ |
|---|---|---|---|
| closed_trades | 391 | 405 | +14 |
| decisiones BUY | 457 | 457 | 0 |
| gross_execution_pnl | −1.294758 | −1.982729 | −0.687971 |
| fees | 15.641833 | 16.201230 | +0.559397 |
| slippage | 3.128367 | 3.240246 | +0.111879 |
| net_pnl | −16.936591 | −18.183960 | −1.247369 |
| expectancy | −0.043316 | −0.044899 | −0.001583 |
| profit_factor | 0.4307 | 0.4184 | −0.0123 |
| win_rate | 0.4629 | 0.4469 | −0.0160 |
| max_drawdown_abs | 16.936591 | 18.183960 | +1.247369 |
| avg_holding_ms | 6 267 774.9 | 5 171 540.5 | −1 096 234.4 |

**Lectura:** mismo nº de BUY (457) y variación pequeña de población (391→405), pero el
resultado NEW empeora ~1.25: `take_profit` 2→4, `stop_loss` 115→155, y `strategy_exit` 246
frente a los 274 `llm_sell` de OLD. Estrategia de reversión a la media: el fill intrabar y la
evaluación protectora intrabar se materializan distinto al cierre de vela.

## 4. Diferencias OLD→NEW transversales

1. **Reloj de ejecución:** OLD decide y ejecuta al `candle.close` (un reloj); NEW decide al
   cierre confirmado y ejecuta en el **primer trade elegible** (dos relojes), con evaluación
   de SL/TP/trailing intrabar. Cambia el subtipo de salida y el holding.
2. **Presentación de salidas:** `llm_sell` (OLD raw) ⇒ `strategy_exit`; `strategy_exit` es el
   raw de NEW. No se modifican los raw.
3. **Costes:** fees ≈ iguales por operación; al aumentar el nº de operaciones (donchian) los
   costes agregados suben proporcionalmente.
4. **Reentradas:** al liberar la posición antes, NEW permite reentrar; efecto nulo/pequeño en
   baseline y bollinger, grande en donchian.
5. **Rechazos RiskEngine:** 0 en las 3 corridas NEW (no hubo `max_daily_loss`/`max_drawdown`).
6. En las 6 combinaciones el **net realizado es negativo** y `final_equity < 1000`; el
   mecanismo muestra costes+fees dominando el neto. **No** es una conclusión de rentabilidad.

## 5. Comparabilidad y alcance

- `DEVELOPMENT_ONLY=YES` — in-sample, sobre el Gold `DEVELOPMENT` (ordering_fidelity `PARTIAL`).
- `POPULATIONS_DIRECTLY_COMPARABLE=NO` — distinto reloj, fills, reentradas y subtipo de salida.
- `OOS_CONCLUSION=NO` — sin walk-forward ni holdout; nada de viabilidad futura.
- `WF_READS=0` · `HOLDOUT_READS=0`.
- Phase 21R (baseline 634 / donchian 1086 / bollinger 460):
  `REFERENCE_ONLY_DIFFERENT_BOUNDARY_WINDOW=YES`.

## 6. ¿Bug o repetición obligatoria?

- Sin fallos de paridad, sin discrepancias de hash, sin `.part`, ledger M7 legacy intacto,
  paper/certification intactos, sin lecturas WF/holdout.
- Consistencia interna de los 12 artefactos: **YES**.
- **No** hay evidencia que obligue a repetir el replay.
  `REPLAY_RERUN_REQUIRED=NO`.
- Nota de honestidad: no se ejecutó una segunda corrida completa de 647 días para un
  contraste de determinismo a esa escala (solo smoke de 3 días); la determinismo está
  garantizada por diseño y por el smoke, y no es motivo de repetición.

## 7. Conclusión M9 (strategy-validation)

La integración de las 3 estrategias congeladas con el Trade-Level Replay M7 y su comparación
OLD-vs-NEW sobre la ventana común de 647 días está **técnicamente completa a nivel
DEVELOPMENT**: paridad de señales PASS, artefactos económicos completos y consistentes,
ledgers reproducibles con hash, sin lookahead (reloj de decisión sólo con velas confirmadas)
y sin tocar WF/HOLDOUT. Queda listo para preparar un **commit candidate** de documentación/artefactos.

---

## SALIDA

```text
M9B_REVIEW=PASS
REPLAY_RERUN_REQUIRED=NO
ARTIFACTS_CONSISTENT=YES
BASELINE_REVIEW=PASS
DONCHIAN_REVIEW=PASS
BOLLINGER_REVIEW=PASS
DEVELOPMENT_ONLY=YES
OOS_CONCLUSION=NO
READY_FOR_M9_COMMIT_CANDIDATE=YES
```

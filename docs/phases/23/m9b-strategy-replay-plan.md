# M9-B — Strategy Replay Compatibility Gate (plan de diseño, NO implementado)

**Estado:** diseño completado · **Rama:** `medalion` @ `5dbc1c3c871a743cd0a54274fcc4fdce18e54d1f`
**Fecha:** 2026-09-28 · **Alcance M9-B0:** análisis + este documento. **Sin implementación, sin replay de 647 días, sin cambios en estrategias, sin commit/push, sin `MARK-DONE` de M9, sin `gate-request` de la fase 23.**

---

## 1. Objetivo

Analizar y diseñar (antes de ejecutar FULL DEVELOPMENT) la integración de las tres
estrategias congeladas — `EmaRsiBaseline`, `EthDonchianBreakout`,
`EthBollingerMeanReversion` — con el **Trade-Level Replay M7**
(`src/infrastructure/medallion/replay.py`), preservando la lógica de estrategia y las
reglas económicas de Phase 22-B, y verificando que la integración no introduzca
lookahead.

## 2. Contratos verificados en código (evidencia)

### 2.1 Dos interfaces distintas

| | Interfaz de estrategia | Interfaz de replay |
|---|---|---|
| Tipo | `Strategy.on_candle(candle: Candle) -> Signal` (`src/domain/trading/strategy.py:85`) | `DecisionProvider.decide(*, candle_index, decision_ts, reference_price, atr_value, context) -> Decision \| None` (`src/infrastructure/medallion/replay.py:198-209`) |
| Entrada | una vela 15m `Candle` | metadatos de la vela ya confirmada + ATR + contexto |
| Salida | `Signal(timestamp_ms, action, intensity, reason)` | `Decision(action, signal_ts, reference_price, candle_index, atr)` o `None` (HOLD) |
| Posición/riesgo | fuera del alcance de la estrategia (autoridad: RiskEngine/paper) | motor: fills, SL/TP/trailing, contabilidad |

No existe hoy ningún adaptador `Signal → Decision` en el repo (única implementación de
`DecisionProvider`: `ScriptedScheduleProvider`, `replay.py:288`).

### 2.2 Relojes y timestamps (replay M7)

- Motor `_Engine._advance` (`replay.py:891-911`): itera velas 15m **confirmadas** y llama
  `provider.decide(decision_ts=candle.close_time, reference_price=candle.close, atr_value=self._atr[index], …)`
  **exactamente una vez por vela, en orden estricto de `candle_i`** (índice global 0..N-1).
- `Candle.timestamp_ms` = **open_time** (`src/domain/market/candle.py:30`). El propio motor
  construye `Candle(timestamp_ms=c.open_time, …, turnover=0.0)` desde `CandleRow`
  (`replay.py:844-855`) para calcular ATR(14) causal.
- Contexto 1h/4h: `close ≤ decision_ts` vía `bisect` (`replay.py:913-920`).
- Fill: primer trade `>= trigger` (`FILL_RULE = "first eligible trade from the decision timestamp"`, `replay.py:100`); decisión nunca se ejecuta retrospectivamente (doc `docs/design/medallion-replay-architecture.md` §8.3, §10).
- Contabilidad: `net = gross − slippage − fees` (`replay.py:16-19`).

### 2.3 Las tres estrategias (comportamiento verificado, NO a modificar)

| Estrategia | Construcción | `on_candle` | Warmup / restricciones |
|---|---|---|---|
| `EmaRsiBaseline` (`strategy.py:112-137`) | incremental (trackers de estado) | devuelve señales al cierre de cada vela | `HOLD reason="warmup"` hasta que EMA20/EMA50/RSI14 estén definidas |
| `EthDonchianBreakout` (`eth_donchian_breakout.py:46-81`, 83-113) | **preloaded** `candles=` (tupla completa) | exige `candle == self._candles[self._index]` y avanza índice; `ValueError` si se agota o no coincide | ventanas `index-entry`/`index-exit` **excluyen la vela actual**; ADX causal |
| `EthBollingerMeanReversion` (`eth_bollinger_mean_reversion.py:41-115`) | **preloaded** `candles=` | mismo contrato estricto de secuencia | bandas/ADX precomputados sobre la secuencia completa |

Causalidad de los precomputados: `adx()` declara "cada valor en `i` depende solo de las
velas `0..i`" y `bollinger()`/`atr()` incremental son causales
(`src/domain/market/indicators.py:241-249, 314-321, 122-151`). Ventanas index-exclusive
⇒ **sin lookahead por construcción**; aún así se exige test corruptor (§7).

## 3. Diseño: `StrategyDecisionProvider` (ADAPTER_REQUIRED = YES)

Nuevo módulo (sin tocar las estrategias): `src/infrastructure/medallion/strategy_provider.py`

```python
class StrategyDecisionProvider:
    """Adaptador Strategy(lab/dominio) → DecisionProvider(replay M7). Fail closed."""

    def __init__(self, *, strategy: Strategy, candles: Sequence[Candle]) -> None:
        # candles: tuple(candles) construido UNA sola vez desde CandleRow
        # (misma conversión que _Engine.run: timestamp_ms=open_time, turnover=0.0)
        # Las estrategias preloaded se construyen con ESTA misma secuencia,
        # garantizando orden y valores idénticos (igualdad estructural por vela).

    def decide(self, *, candle_index, decision_ts, reference_price, atr_value, context) -> Decision | None:
        # 1. Invariantes fail-closed:
        #    - candle_index estrictamente creciente y sin huecos (== último+1)
        #    - 0 <= candle_index < len(candles)
        #    - decision_ts == candles[candle_index].close_time (close_time = open_time + 900_000)
        #    - signal.timestamp_ms == candles[candle_index].timestamp_ms (open_time)
        #      → aserción de sanidad; NUNCA se usa como trigger
        # 2. signal = strategy.on_candle(candles[candle_index])
        # 3. Mapeo: HOLD → None; BUY → Decision("buy", ...); SELL → Decision("sell", ...)
        #    acción desconocida → ReplayError (fail closed)
        # 4. signal_ts := decision_ts  (siempre; ver §4)
        # 5. reference_price := argumento del motor (close confirmado)
        # 6. atr := atr_value del motor (ATR 14, causal; NO re-calcular en el adapter)
        # 7. context se ignora: las tres estrategias son 15m-only (no usan 1h/4h)
```

Notas de diseño:

- **Genérico sobre `Strategy`** (Protocol estructural): el adaptador no importa
  `lab.strategies`; la construcción de la estrategia concreta (y de su config congelada)
  la hace quien ensambla (runner/CLI de M9-B). Evita dependencia infrastructure→lab.
- Las tres estrategias avanzan exactamente una vela por llamada y el motor garantiza
  exactamente una llamada por vela en orden ⇒ el contrato estricto de las preloaded se
  satisface sin buffering. Si alguna futura llamada fuera repetida/desordenada, el
  adaptador falla cerrado antes de corromper el estado.
- `signal.action` es `Action` (StrEnum "buy"/"sell"/"hold") ⇒ el mapeo a
  `Decision.action` usa `signal.action.value` y valida contra `{"buy","sell"}`.

## 4. Mapeo de timestamps (SIGNAL_TIMESTAMP_MAPPING)

| Concepto | Fuente | Regla |
|---|---|---|
| `Signal.timestamp_ms` (estrategia) | `Candle.timestamp_ms` = **open_time** | solo aserción de sanidad (`== decision_ts − 900_000`); **nunca** es `signal_ts` |
| `decision_ts` (motor) | `candle.close_time` (vela confirmada) | instante de la decisión |
| `Decision.signal_ts` | — | **`:= decision_ts` (close_time) SIEMPRE** (requisito: `signal_ts == decision_ts`) |
| `Decision.reference_price` | `candle.close` (close confirmado) | lo aporta el motor |
| `entry_signal_timestamp` / `entry_trigger_timestamp` | `signal_ts` | idénticos (fill en el primer trade `>= signal_ts`) |

**Por qué no copiar `Signal.timestamp_ms`:** usar open_time como trigger adelantaría el
trigger 15 minutos y permitiría fills en trades ocurridos *dentro* de la vela de decisión
→ lookahead. Esto se cubre con el test de §7 (`entry_fill_timestamp >= decision_ts`).

## 5. Escenario económico M9-B (PHASE22B_PARAMETERS_PRESERVABLE = YES)

`ReplayScenario` es un dataclass frozen con campos explícitos (`replay.py:264-277`) ⇒
**no hace falta tocar el motor** para fijar costes/riesgo:

| Parámetro | Phase 22-B (referencia) | Default M7 | Escenario M9-B propuesto |
|---|---|---|---|
| `stop_atr_multiplier` | 2.0 | 2.0 | 2.0 |
| `take_profit_r_multiple` | **2.0** | 1.5 | **2.0** |
| `trailing_atr_multiplier` | **3.0** | 1.0 | **3.0** |
| `fee_rate` | 10 bps (taker 10 / maker 10) | 0.001 (10 bps) | 0.001 (idéntico) |
| `slippage_bps` | **2.0** | 5.0 | **2.0** |
| ATR period | 14 | 14 | 14 |
| Sizing | **RiskEngine dinámico** (`capital=1000`, intensidad `MEDIUM`, drawdown scale) | `quantity=0.01` fija | **RiskEngine dinámico** (§6) |
| Intensidad | `Intensity.MEDIUM` (`phase22b_atr_exit_experiment.py:162`) | n/a | `MEDIUM` (consistente con `session_runner.py:135`) |
| `risk.version` | `risk-v2-atr-exit` | `replay-risk-v1` | label nuevo p.ej. `risk-m9b-22b-parity-v1` (valores 22B, versionado trazable) |
| `scenario_id` / `strategy_version` | — | `scripted-default-v1` / `scripted-schedule-v1` | p.ej. `m9b-22b-parity-v1` / `strategy.version` real (`baseline-v1`, `eth-donchian-breakout-v1`, `eth-bollinger-mean-reversion-v1`) |

**Prohibido:** ejecutar M9-B silenciosamente con los defaults M7 (tp 1.5 / trailing 1.0 /
slippage 5 bps / qty fija). Si por restricción de esfuerzo se usara algún default, deberá
declararse explícitamente en evidencia (no es el plan recomendado).

## 6. Reutilización del Risk Engine (RISK_ENGINE_REUSE / DYNAMIC_SIZING_REUSABLE)

**Ya reutilizado por el motor M7 sin cambios:** `initial_stop`, `take_profit`,
`update_trailing` (`replay.py:43, 992-993`) — mismas fórmulas que usa `RiskEngine`.

**Sizing dinámico — reutilizable como funciones de dominio:** `RiskEngine.evaluate`
(`src/domain/risk/engine.py:66`) + `compute_position_size`
(`src/domain/risk/sizing.py:26`) son puros y no duplican fórmulas. `PaperEngine.on_price`
(`src/application/services/paper_engine.py:132-177`) muestra el patrón ya probado:
`TradeProposal` + `PortfolioRiskState(open_positions, realized_pnl_today, peak_equity, equity, kill_switch)` → `RiskVerdict.size/stop_loss/take_profit`.

**Diagnóstico honesto (reporte previo a implementar, exigido por el encargo):**
preservar el sizing dinámico 22B **sí exige modificar el replay M7** — `Decision` no
lleva quantity, `_open_position` usa `scenario.quantity` fijo (`replay.py:995`) y el
motor no mantiene estado de portfolio (equity/pnl diario/peak/kill switch; solo registra
`net_pnl` por trade cerrado). **M7_ENGINE_CHANGES_REQUIRED = YES**, alcance estimado
**moderado y localizado** (no es un rediseño):

1. `ReplayScenario`: campo nuevo `sizing_mode: "fixed" | "risk_engine"` con default
   `"fixed"` (los runs scripted M7 existentes quedan byte-idénticos).
2. `Decision`: campo opcional `intensity` (default `MEDIUM`; hoy fijo en el patrón
   `session_runner`). *Alternativa válida:* intensidad fija en el escenario (0 cambios en
   `Decision`).
3. `_Engine`: mantener `PortfolioRiskState` (realized acumulado al `_finish`, peak
   equity, pnl diario por fecha UTC del fill — determinista, sin wall-clock; kill switch
   `inactivo`) y llamar `RiskEngine.evaluate` al abrir posición; si `approved=False`
   ⇒ soltar la decisión con contador nuevo `decisions_rejected` (motivo auditable).
   La quantity resultante reemplaza `scenario.quantity` solo en modo `risk_engine`.
4. `ledger_payload`: añadir `sizing_mode` a `run_meta` (campo nuevo, no rompe el
   contrato de registros).

**Puntos de decisión a resolver al implementar (presentados, no decididos aquí):**

- **Momento de evaluación:** 22B/PaperEngine evalúa por vela con precio de cierre;
  propuesta = evaluar al **fill** (reloj de ejecución) con el precio de trade, o al
  decisión con `candle.close` para máxima paridad 22B. Recomendación: decisión +
  `candle.close` (paridad con 22B), documentando que el fill usa ese quantity.
- **Base del stop inicial:** el motor M7 calcula `initial_stop` desde
  `entry_execution_price` (`replay.py:992`); 22B identificaba el stop desde
  `entry_reference_price` (close). Diferencia = slippage (≤2 bps). Recomendación:
  **mantener la semántica M7** (execution-based, ya testeada) y registrar la desviación
  ≤2 bps respecto de 22B en la evidencia.
- **Guards adicionales:** con `RiskEngine` activo aparecen rechazos que 22B/PaperEngine
  ya sufría (`max_daily_loss`, `max_drawdown`, `stop_unavailable`) y que el replay
  scripted no tenía ⇒ cambia la población de trades (además del reloj). Debe reportarse
  como parte de la comparabilidad (§9), nunca silenciosamente.

**Alternativas descartadas:** (a) `quantity` fija del default M7 — rompe paridad 22B sin
declararlo; (b) sizing en el provider — duplicaría contabilidad de portfolio (prohibido:
"no duplicar fórmulas").

## 7. Tests previstos (unidad, sin mirar el futuro)

Base existente: `tests/test_trade_replay.py` (incluye corruptores
`test_future_candle_corruption_does_not_change_records`, `test_decisions_use_candle_close_not_future_candles`,
`test_entry_fills_at_first_trade_at_or_after_decision_ts`), `tests/test_no_lookahead.py`,
`tests/test_backtest_no_lookahead.py` (patrón prefix/`replay_truncated`).

1. **Paridad de decisiones:** por cada estrategia, `provider.decide(...)` produce
   exactamente la misma secuencia de acciones que llamar `strategy.on_candle(...)`
   directamente sobre la misma lista de velas (el adaptador no altera lógica).
2. **Mapeo de timestamps:** para toda decisión, `signal_ts == decision_ts ==
   close_time` y `entry_fill_timestamp >= entry_signal_timestamp`; un corruptor que
   modifique trades entre open y close de la vela de decisión no puede generar fills
   anteriores al close confirmado.
3. **Corruptor temporal (las 3 estrategias + adapter):** mutar velas con índice `> i`
   no cambia ninguna decisión en índices `<= i` (propiedad prefix); mutar el contexto
   1h/4h futuro tampoco (las 3 estrategias lo ignoran — aserción incluida).
4. **Contrato preloaded fail-closed:** secuencia truncada/alterada ⇒ `ValueError` de la
   estrategia propagada; `candle_index` no contiguo ⇒ `ReplayError` del adaptador.
5. **Determinismo:** mismo dataset + mismo escenario ⇒ payload de ledger byte-idéntico
   (patrón `test_engine_determinism_same_input_same_payload`).
6. **Sizing sin duplicación:** quantity producida por el modo `risk_engine` ==
   `RiskEngine.evaluate(...).size.quantity` (la fórmula vive en un solo sitio).
7. **Rechazos auditables:** `max_open_positions`/`max_daily_loss` ⇒ decisión soltada con
   `decisions_rejected` y razón, sin romper fills existentes.

## 8. Smoke test (Gold de 3 días) y FULL DEVELOPMENT posterior

- **Smoke (siguiente paso tras implementar):** replay sobre el Gold de 3 días
  (`gold-replay-a8c49e0be9154194841a97c4f26225a76cef9fba8d9a6d080198359c124ebdc3`,
  `2023-09-09..2023-09-11`, sin tocarlo): validación FAIL-CLOSED del dataset →
  construir velas 15m → adapter + cada estrategia → escenario 22B → ledger por estrategia
  con todos los `REQUIRED_RECORD_FIELDS` (`replay.py:113-141`), catálogo de
  `exit_reason` cerrado, `M7` sin warnings. Evidencia vía `harness/scripts/evidence.sh 23`.
  Requiere un runner pequeño (hoy el motor M7 solo se ejércita desde tests): candidato
  `harness/scripts/m9b_strategy_replay.py` o subcomando CLI nuevo.
- **FULL DEVELOPMENT (M9-B final, tras smoke PASS):** mismo flujo sobre
  `gold-replay-5ca68f44c37d2321f56a10ecbc08bc0584d70c17826f07604dbba77a8b71134a`
  (647 días, `manifest c095d574…`), un ledger por estrategia, métricas con fees +
  slippage + coste, y comparación **descriptiva** con 22B (§9). Requiere gate M9-B0
  aprobado primero.

## 9. Comparabilidad de poblaciones (POPULATIONS_DIRECTLY_COMPARABLE = NO)

No son directamente comparables por tres motivos acumulados:

1. **Reloj:** 22B ejecutaba por cierre de vela (PaperEngine); M9-B ejecuta por trades
   (trigger vs fill, `TRADE_SEQUENCE_TAKER_PROXY`) ⇒ cambian fills, stops/TP intrabar,
   duración y reentradas.
2. **Riesgo/costes:** parámetros 22B preservados, pero los *guards* del RiskEngine y el
   momento de evaluación se materializan de otra forma (§6).
3. **M7 scripted:** poblaciones previas del replay usaban scenario y estrategia
   guionados distintos.

Conservar parámetros permite únicamente una **comparación descriptiva más limpia**
(qué cambia atribuible al reloj), nunca igualdad de poblaciones.

## 10. Archivos esperados de cambio en M9-B (IMPLEMENTATION — fuera de M9-B0)

| Archivo | Cambio |
|---|---|
| `src/infrastructure/medallion/strategy_provider.py` | **nuevo** — `StrategyDecisionProvider` (§3) |
| `src/infrastructure/medallion/replay.py` | `ReplayScenario.sizing_mode`; `Decision.intensity` (o fijo en escenario); estado de portfolio + `RiskEngine.evaluate` en `_open_position`; contador `decisions_rejected`; `sizing_mode` en `run_meta` (§6) |
| `harness/scripts/m9b_strategy_replay.py` (o CLI nuevo) | **nuevo** — runner: validate → load → adapter → engine → ledger (§8) |
| `tests/test_strategy_provider.py` | **nuevo** — paridad, mapeo de timestamps, fail-closed (§7.1, 7.2, 7.4) |
| `tests/test_strategy_replay_no_lookahead.py` | **nuevo** — corruptores temporales (§7.3) |
| `tests/test_trade_replay.py` | ampliar: sizing_mode, rechazos, determinismo (§7.5-7.7) |
| `docs/design/medallion-replay-architecture.md` | actualizar escenario/§9 si se añade `sizing_mode` |

**No se tocan:** `src/lab/strategies/*`, `src/domain/trading/strategy.py`,
`src/domain/risk/*` (reutilización pura), datasets Gold/Silver/Bronze, certificación.

## 11. SALIDA (bloque de veredicto M9-B0)

```text
M9B0=PASS
STRATEGY_LOGIC_CHANGES_REQUIRED=NO
ADAPTER_REQUIRED=YES
SIGNAL_TIMESTAMP_MAPPING=Decision.signal_ts:=decision_ts(close_time); Signal.timestamp_ms(open_time) solo asercion == decision_ts-900000; nunca como trigger; reference_price=candle.close; atr del motor(14)
RISK_ENGINE_REUSE=YES (initial_stop/take_profit/update_trailing ya en motor; RiskEngine.evaluate+compute_position_size reutilizables como funciones)
DYNAMIC_SIZING_REUSABLE=YES (funciones de dominio; wiring en replay = cambio M7 reportado)
PHASE22B_PARAMETERS_PRESERVABLE=YES (ReplayScenario explicito: stop 2.0 / tp_r 2.0 / trailing 3.0 / fee 0.001 / slippage 2.0 bps / intensity MEDIUM / capital 1000; NO usar defaults M7)
M7_ENGINE_CHANGES_REQUIRED=YES (moderado y localizado: sizing_mode + estado portfolio + RiskEngine al abrir + decisions_rejected + run_meta.sizing_mode; detail en §6)
EXPECTED_FILES_TO_CHANGE=src/infrastructure/medallion/strategy_provider.py (nuevo), src/infrastructure/medallion/replay.py, harness/scripts/m9b_strategy_replay.py (nuevo), tests/test_strategy_provider.py (nuevo), tests/test_strategy_replay_no_lookahead.py (nuevo), tests/test_trade_replay.py, docs/design/medallion-replay-architecture.md
POPULATIONS_DIRECTLY_COMPARABLE=NO
READY_FOR_M9B_IMPLEMENTATION=YES (sujeto a aprobacion humana de este plan)
```

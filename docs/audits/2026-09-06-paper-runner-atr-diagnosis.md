# Auditoría — Paper-runner: 0 trades por `atr=None` (diagnóstico verificado 2026-09-06)

- **Fecha:** 2026-09-06 06:30 UTC
- **Alcance:** validar el diagnóstico de un modelo previo (deepseek) sobre por qué el paper
  trading real en `lenovosrv` produce 0 trades. Revisión independiente de cada afirmación
  contra el código **desplegado** y contra la base de datos.
- **Método:** inspección read-only del runtime (`lenovosrv` 192.168.100.24) + diff de código
  desplegado vs. ramas + replay local determinista de las mismas velas reales.
- **Rama desplegada (fuente de verdad):** `feature/paper-regime-certification` — el contenedor
  `self-evaluating-trading-agent-paper-runner-1` coincide **md5 a md5** con esa rama
  (`paper_runner.py` 366 líneas con regimes, `cli/paper_runner.py` 171 líneas con supervisor).
  ⚠️ El repo local en `feature/phase-08-llm-decision-agent` tiene `paper_runner.py` de 262 líneas
  SIN supervisor ni regimes — **no es** lo que corre en producción.

---

## 1. Verificación del estado (2026-09-06 06:29 UTC)

| Elemento | Hallazgo verificado |
|---|---|
| `paper-runner-1` | Contenedor "Up"; tras `docker restart` manual quedó **vivo y procesando** (última vela confirmada 06:00 escrita). |
| Post-crash | Crash del 09-06 ~00:51 UTC: `WebSocketDisconnected 1011 keepalive ping timeout` + `Temporary failure in name resolution` (DNS) → supervisor agota reintentos → proceso muere. |
| DB `paper_trade_events` | 402 eventos (1 sesión `paper-baseline-15m-ethusdt`), contiguos cada 15 min del 09-02 01:15 al 09-06 05:45 (1 solo hueco >16 min). |
| Decisiones en DB | **1 BUY + 7 SELL + 394 HOLD** · fills **0** · equity congelada en $1000. |
| `certification-state.json` | `trade_count: 0`, `calendar_days: 4`, 6 regímenes confirmados, `periodic_reports` OK → certificación PENDING (no puede avanzar con 0 trades). |
| `market_candles` | **0 filas** (tabla de persistencia de velas vacía; el runner no la alimenta). |

---

## 2. Revisión punto por punto del diagnóstico previo

### Punto 1 — "Restart; cada desconexión WS mata el proceso; parchear `ws.py:close()`"
**Veredicto: PARCIALMENTE INCORRECTO.** El código desplegado **ya reconecta**:

- `cli/paper_runner.py` (desplegado) inyecta `recover=supervisor.run_once_until_connected`
  y `_run_loop` captura `WebSocketDisconnected` → `await recover()` (líneas 53–60, 110, 139).
- `connection_supervisor.py`: `ConnectionSupervisorConfig(max_attempts=5, backoff 1→30s)`.
- La causa del crash del 09-06 ~00:51 fue **DNS/red caída de forma sostenida**:
  el supervisor intentó reconectar 5 veces (backoff ≤ ~1 min), agotó intentos y lanzó el
  último error. El proceso no muere por *cada* desconexión; muere cuando la reconexión falla
  repetidamente.
- **Bug real pero secundario:** `websockets` 17.0.1 lanza `AttributeError: 'connect' object has
  no attribute 'connection'` en `asyncio/client.py:626` (`__aexit__` hace `del self.connection`)
  cuando la conexión **nunca se estableció**. Se dispara en `infrastructure/bybit/ws.py:39-43`
  (`close()` → `self._cm.__aexit__(None,None,None)`), dentro del `finally` de `_run`. **Enmascara
  el error primario** y convierte un shutdown razonable en un crash feo. Vale la pena parchear
  `ws.py:close()` para tolerar `_ws is None`, pero NO es la causa raíz del 0-trades ni del crash.

### Punto 2 — "No es umbrales; es `atr=None` → jamás hay BUY"
**Veredicto: CORRECTO — es la causa raíz del 0 trades (fills).** Verificado:

- `paper_runner.py` desplegado, `handle_kline` (línea 319) construye `PaperEngine.on_price(...)`
  pasando **`atr=None` SIEMPRE** (línea 339). El runner realtime no calcula ATR.
- `domain/risk/engine.py:87-88`: con `RiskConfig.stop_loss_required=True` (default, config.py:22)
  y `atr is None` → rechaza **todo BUY** con `stop_unavailable`.
- DB: el único BUY (09-05 13:00) → rechazado `stop_unavailable`. Los 7 SELL → rechazados
  `no_position_to_reduce` (nunca hay posición porque nunca se compra). Consecuencia en cascada.
- Asimetría confirmada: `interfaces/cli/paper_session.py:77,108` (replay determinista sobre
  dataset) **sí** calcula `atr(candles)` y pasa `atr=atr_series[i]`. Solo el runner WS en vivo
  omite el ATR. El backtest también lo calcula. El arreglo debe replicar eso en el flujo WS.
- El `RegimeClassifier` del runner ya mantiene `deque(maxlen=100)` de velas por símbolo
  (`paper_runner.py:301-317`) → hay buffer disponible para derivar ATR sin nueva infra.

**Matiz que el diagnóstico previo NO capturó (discrepancia de señales):**
- Replay local independiente de las **mismas 402 velas** (Bybit REST, 09-02 01:15→09-06 05:30)
  con `EmaRsiBaseline` idéntico produce **2 BUY + 7 SELL** (9 señales).
- Producción solo registró **1 BUY** (perdió el BUY del 09-03 03:00) aunque los SELL coinciden.
- Explicación probable: los trackers EMA/RSI de `EmaRsiBaseline` son **estado en memoria**;
  cada reinicio del proceso (p. ej. el del 09-02 21:14 al recrear el contenedor con la rama de
  regimes) **resetea el warmup** (~50 velas ≈ 12.5 h). Los reinicios reducen señales además del
  bloqueo ATR, y no son visibles como huecos porque las velas siguen escribiéndose tras reconectar.

### Punto 3 — "DNS/Network"
**Veredicto: CORRECTO.** El 09-06 resuelve `stream.bybit.com` → IPv4 `18.161.170.x`
(CloudFront) tanto en el host como dentro del contenedor (`getent` + `getaddrinfo` OK).
`daemon.json` de Docker sin override DNS. El fallo fue transitorio (~00:51). El `1011 keepalive
ping timeout` apunta a un corte de red pasajero del servidor, no a un problema de configuración.

---

## 3. Conclusión

El "0 trades" se explica por la combinación de:
1. **`atr=None` en el flujo WS** (causa principal): el Risk Engine rechaza todo BUY
   (`stop_unavailable`) → 0 fills → equity congelada → certificación PENDING sin poder avanzar.
2. **Warmup-reset por reinicios** (secundario pero real): reduce el nº de señales emitidas
   respecto al potencial de la estrategia sobre el mismo rango de datos.
3. El ritmo intrínseco de la baseline (EMA20/50+RSI sobre ETHUSDT 15m ≈ 1–2 BUY cada 4 días)
   es bajo por diseño — motivo original del proyecto de Historical Experience Replay.

### Ramas / dónde aplicar el fix
- **NO** tocar la versión en Paper Trading sin nueva versión de estrategia (regla arnés).
- El fix de ATR y el parche de `ws.py:close()` deben ir en **`feature/paper-regime-certification`**
  (o una rama derivada), NO en `feature/phase-08-llm-decision-agent` que no refleja el despliegue.
- Cualquier cambio a la versión sometida a Paper Trading exige nueva `strategy_version`/GATE.

### Evidencia
- DB `paper_trade_events` (402 eventos; 1 BUY + 7 SELL; 0 fills) — consultado 2026-09-06 06:00 UTC.
- `certification-state.json` (`/app/certification/`) del contenedor.
- Replay local determinista (2 BUY + 7 SELL sobre 402 velas reales) — script
  `/tmp/opencode/replay_strategy_test.py`.
- Diff md5 del contenedor vs rama `feature/paper-regime-certification`.

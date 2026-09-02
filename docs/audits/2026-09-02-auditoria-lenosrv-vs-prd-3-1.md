# Auditoría — lenovosrv vs. Objetivos Funcionales (PRD §3.1)

- **Fecha:** 2026-09-02
- **Alcance:** lo implementado/desplegado en el servidor `lenovosrv` (192.168.100.24) frente a los objetivos funcionales de la sección 3.1 del PRD.
- **Método:** inspección read-only del runtime (contenedores, imagen, DB, logs) + lectura del código vigente de la rama `feature/paper-regime-certification`.
- **Fuente de verdad del producto:** `docs/PRD — Self-Evaluating Trading Agent.md` §3.1.

---

## 1. Evidencia del estado en lenovosrv (2026-09-02 18:32 UTC)

| Elemento | Hallazgo |
|---|---|
| Contenedores activos | `paper-runner` (Up 12 h, `restarts=2`) + `postgres` (`pgvector:pg16`, healthy). Sin API/dashboard, sin Prometheus/Grafana. |
| Imagen `paper-runner` | Creada 2026-09-01 20:52 local (commit `ef08869`). **No incluye** `regime_confirmation.py` (anterior a la rama actual). |
| Config runtime | `TRADING_MODE=paper`, `LIVE_TRADING_ENABLED=false`, `PAPER_DECISION_SOURCE=baseline`, `--symbols ETHUSDT --timeframe 15m`. |
| Base de datos | 8 tablas: `alembic_version`, `dataset_manifests`, `market_candles`, `memory_items`, `orderbook_feature_windows`, `paper_trade_events`, `reflections`, `system_state`. |
| Actividad real | 69 eventos, **todos `HOLD`**, equity 1000 fijo, 0 trades. Rango 2026-09-02 01:15–18:15 UTC (con huecos → caídas intermitentes). |
| Último log runner | Crash `WebSocketDisconnected: keepalive ping timeout` propagado → proceso muere (no reconecta). |
| Volúmenes | `/app/certification/certification-state.json` **no existe**; `/app/reports/paper` **vacío**. |

### Causa raíz del `todo HOLD`
`EmaRsiBaseline` (EMA 20/50 + RSI exit) necesita warmup de ~50 velas (≈12.5 h a 15m). Los reinicios (crash WS → restart policy) resetean el warmup del `PaperRunner`, así que nunca se alcanzan señales BUY/SELL.

---

## 2. Matriz por objetivo funcional (§3.1)

Leyenda: **C** = implementado en el código del producto (fases 00–15 aprobadas) · **D** = desplegado/operativo en lenovosrv · **G** = gap.

| # | Objetivo | Estado | Notas |
|---|---|---|---|
| 1 | Consumir datos reales de producción Bybit | C ✅ / D 🟡 | Solo klines ETHUSDT WS; sin order book en runtime |
| 2 | Analizar ETH/USDT | C ✅ / D ✅ | Único símbolo activo (15m) |
| 3 | BTC/USDT solo como contexto | C ✅ / D ❌ **G** | Runner corre solo `ETHUSDT`; BTC no consumido |
| 4 | Market state multi-timeframe | C ✅ / D ❌ **G** | Runtime fijo a 15m (sin 1h/4h) |
| 5 | Indicadores y features | C ✅ / D 🟡 | Solo los del baseline; sin features order book/BTC |
| 6 | Clasificar regímenes de mercado | C ✅ / D ❌ **G** | Clasificador existe; la imagen no trae el tracker de confirmación; sin `market_regimes`; 0 regímenes confirmados |
| 7 | Decisiones BUY/SELL/HOLD | C ✅ / D 🟡 | 69/69 HOLD — genera decisiones pero sin trades |
| 8 | LLM como decisor supervisado | C ✅ / D ❌ **G** | Runtime en `baseline`; sin llamadas LLM en el server |
| 9 | Memoria PostgreSQL+pgvector | C ✅ / D 🟡 | Tabla vacía; nada la usa en runtime |
| 10 | Recuperar experiencias similares | C ✅ / D ❌ **G** | Sin datos → sin recuperación |
| 11 | Evaluar trades automáticamente | C ✅ / D ❌ **G** | 0 trades cerrados → sin outcomes/MFE/MAE |
| 12 | Reflexiones estructuradas | C ✅ / D ❌ **G** | Tabla `reflections` vacía |
| 13 | Proponer mejoras de estrategia | C ✅ / D ❌ **G** | No operativo |
| 14 | Bloquear auto-aplicación de mejoras | C ✅ / D ⚪ | Garantía de diseño; sin uso real |
| 15 | Risk Engine determinista | C ✅ / D 🟡 | Presente; sin trades que lo ejerciten |
| 16 | Backtesting | C ✅ / D ⚪ | Herramienta local (no servicio en server) |
| 17 | Market replay | C ✅ / D ⚪ | Herramienta local (REPLAY=PASS fase 15) |
| 18 | Paper trading sobre datos reales | C ✅ / D ✅ | **Único objetivo operativo hoy** |
| 19 | Bybit Testnet (posterior) | C ✅ / D ⚪ | Verificado fase 12; no en runtime |
| 20 | Integración LIVE técnica | C ✅ / D ✅ | Gateado; `LIVE_TRADING_ENABLED=false` |
| 21 | LIVE deshabilitado por defecto | C ✅ / D ✅ | Correcto |
| 22 | Dashboard operativo | C ✅ / D ❌ **G** | FastAPI+Jinja2+HTMX **no corre** en el server |
| 23 | Observabilidad técnica | C ✅ / D ❌ **G** | Prometheus/Grafana/OTel **no corren**; crash sin alertas |
| 24 | Analítica cuantitativa | C 🟡 / D ❌ **G** | Métricas §45 existen; informes periódicos sin emitir (`reports/` vacío) |
| 25 | Comparar estrategias/modelos | C ✅ / D ⚪ | Herramienta local (ML fase 07, comparativas fase 09/14) |

---

## 3. Gaps identificados

### 3.1 Despliegue en lenovosrv
- **G1 — Stack mínimo:** solo `paper-runner` + `postgres`. Dashboard/API (FastAPI) y observabilidad (Prometheus/Grafana) no están desplegados, aunque el código y el `compose.yaml`/`deploy/` locales los definen.
- **G2 — Imagen desactualizada:** la imagen no incluye `regime_confirmation.py` (confirmación de regímenes) ni las correcciones de la rama actual.

### 3.2 Operatividad (bloquea la Fase 16)
- **G3 — Certificación estancada:** 0 trades, 0 días, 0 regímenes; todo HOLD. El entregable exige 30 días, 200 trades y 2 regímenes.
- **G4 — Informes periódicos sin generar:** `reports/paper` vacío y `certification-state.json` ausente en el contenedor (bloqueo `informes-periodicos`).
- **G5 — Confiabilidad:** crash por keepalive ping timeout del WS propagado → muerte del proceso (reinicios=2, huecos en la serie de eventos). Sin reconexión en ese camino.

### 3.3 Funcionalidad no ejercitada en el server
- **G6 — Contexto/estado incompletos:** BTC, multi-timeframe 1h/4h y order book no operando (solo ETHUSDT 15m klines). Prerrequisito del MarketState del LLM.
- **G7 — Ciclo cognitivo inactivo:** LLM, memoria/RAG, evaluador, reflexiones y mejoras implementadas pero sin uso (baseline + 0 trades).
- **G8 — Persistencia reducida:** 8 tablas vs. modelo conceptual §55 (sin `market_regimes`, `decisions`, `audit_events`, `approvals`, `risk_configs`, `experiments`, etc.). Verificar si decisiones/auditoría del ciclo se persisten o se pierden.

### 3.4 Seguridad
- **S1 — Credencial en texto plano:** el password sudo de `lenovosrv` quedó embebido en evidencia histórica de Fase 16 (p. ej. `deploy-applied-lenosrv.log`). Requiere rotación (usuario) y saneado de archivos.

---

## 4. Lectura global

La **implementación en código es ~completa** para los objetivos §3.1 (fases 00–15 aprobadas). El **despliegue operativo en lenovosrv cubre 1 de 25 objetivos** (paper trading baseline sobre ETH/USDT), con el resto presente en la imagen pero no operando. El ML Baseline (fase 07) no es un objetivo §3.1 directo: es comparador offline contemplado en el objetivo #25 y en el gate estadístico §47 (Fase 17), no un gap de runtime.

---

## 5. Remediación

- **Remediación 1 (no-LLM, aplicar ahora):** véase `docs/phases/16/remediation-01-sin-llm-7-dias.md`.
- **Remediación 2 (LLM, aplicar al día 7):** véase `docs/phases/16/remediation-02-llm-7-dias.md`.

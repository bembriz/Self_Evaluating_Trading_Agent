# Remediación 2 — Activar el LLM (a aplicar al día 7)

- **Fecha (origen):** 2026-09-02
- **Fecha prevista de aplicación:** tras completar la Remediación 1 y su período de 7 días sin LLM.
- **Origen:** `docs/audits/2026-09-02-auditoria-lenosrv-vs-prd-3-1.md` (gaps G6–G8 y objetivo #8; filas C ✅ con D ❌ del ciclo cognitivo).
- **Prerrequisito:** Remediación 1 APPROVED y cierre del brazo determinista documentado (R1.7) como comparador.

---

## Contexto técnico verificado

- `PaperRunnerConfig.validate_safe()` hoy **solo acepta `decision_source="baseline"`** (`src/application/services/paper_runner.py:277`) y **no invoca `DecisionAgent`**: el LLM está implementado como servicio aparte (`decision_agent.py`, `infra/llm/deepseek.py`, `infra/llm/prompts.py`, `cost_monitor.py`) pero **no está cableado al runner live**.
- El runner live consume una sola vela 15m de un solo símbolo; no construye `MarketState` multi-timeframe ni contexto BTC.
- Memoria/RAG (pgvector, e5-small 384, guards anti-leakage), evaluador (MFE/MAE) y reflexiones existen (fases 09/11) pero requieren integración al flujo continuo y datos (trades cerrados).
- DB en server: 8 tablas; faltan del modelo §55 entidades que el ciclo LLM usará (`decisions`, `llm_calls`, `risk_evaluations`, etc.) → posible DP + migraciones.

---

## Tareas

### R2.1 — MarketState completo en runtime (G6)
- Activar contexto BTC, multi-timeframe ETH (15m/1h/4h) y order book en el runtime.
- Construir `MarketState` por cada vela 15m cerrada (features + régimen confirmado) como entrada al agente.

### R2.2 — Cablear `decision_source="llm"` en `PaperRunner`
- Ampliar `PaperRunnerConfig`/`validate_safe` para admitir fuente `llm` (y mantener `baseline` para comparaciones).
- Pipeline por vela 15m cerrada: `MarketState` → `DecisionAgent.decide` (DeepSeek, prompt `decision/v001`, `CostMonitor`, presupuestos experiment/monthly) → **fail-safe HOLD** ante timeout/error/schema inválido → `RiskEngine`/`PaperEngine` (autoridad intacta).
- Eventos con `decision_source="llm"` y session_id propio.
- **TDD:** tests con fake LLM (decisión válida, JSON inválido, provider caído → HOLD) + fake stream; verificación de que el Risk Engine conserva autoridad.

### R2.3 — Memoria/RAG y reflexiones en vivo
- Recuperación top-k por similitud con **filtrado temporal (`outcome_timestamp < decision_timestamp`)** y guards anti-leakage; embedding local e5-small (384).
- Tras cerrar cada trade: evaluador (outcome, MFE/MAE) → reflexión estructurada → persistencia en `memory_items`/`reflections` (solo cuando el trade ha terminado).

### R2.4 — Persistencia, config y secrets
- Si aplica: migraciones nuevas (`decisions`, `llm_calls`, `risk_evaluations`, …) → **Dependency Proposal + upgrade/downgrade + gate**.
- Secrets en server: `DEEPSEEK_API_KEY` en `.env` **no versionado**; presupuestos; validar egress DeepSeek desde el contenedor.
- Registrar llamadas LLM (provider, modelo, prompt_hash, tokens, latencia, coste) para reproducibilidad §38.

### R2.5 — Dashboard/API desplegado
- Levantar FastAPI + Jinja2 + HTMX (rol operator, bind localhost, SSH tunnel) en `lenovosrv`: estado del sistema, decisión actual, confidence, régimen, memoria, Risk Engine, costes LLM, kill switch.
- Requiere revisar el arranque (uvicorn sobre `interfaces/api/app.py`; `main.py` no expone subcomando API).

### R2.6 — Recertificación y comparativas
- Cambiar `decision_source` cambia `strategy_hash` → **nueva certificación** para la versión LLM (30 días / 200 trades / 2 regímenes).
- Comparar vs. brazo determinista de los 7 días (R1) y vs. baselines (Buy&Hold, determinista, ML) conforme a experimentos §31 y gate estadístico §47.

### R2.7 — Observabilidad del ciclo LLM
- Métricas de coste/latencia/fallos LLM y alertas en Grafana; revisión de gates 16 → 17.

---

## Gobernanza transversal
- Ningún commit/push/merge/tag/deploy sin autorización explícita.
- Cualquier migración o dependencia nueva → Dependency Proposal + USER GATE (con upgrade/downgrade y tests).
- `LIVE_TRADING_ENABLED=false` y `TRADING_MODE=paper` siempre; el LLM jamás toca el Risk Engine ni habilita LIVE.
- Evidencia con `harness/scripts/evidence.sh`; TDD antes de cada implementación.

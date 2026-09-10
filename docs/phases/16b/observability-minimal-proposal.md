# UAT 16b (redeploy 0.1.1) — Resultados + Observabilidad mínima

> **Fecha:** 2026-09-06 · **Estado:** checklist ejecutado con el usuario · certificación nueva NO iniciada.

## 1. Checklist UAT HITL (7 pasos)

| Paso | Acción | Resultado observado | PASS |
|---|---|---|---|
| 1 | `__version__` | `0.1.1` | ✅ |
| 2 | status/restarts | `running` · `restarts=0` | ✅ |
| 3 | postgres | `accepting connections` | ✅ |
| 4 | logs sin errores | (sin errores) | ✅ |
| 5 | sesiones/eventos | `...-20260906` = 37 eventos, 0 fills, last 17:15 UTC | ✅ |
| 6 | cert-state | `calendar_days=0`, `trade_count=0` (reset) | ✅ |
| 7 | archive INVALIDATED | `certification-state-INVALIDATED-pre-0.1.1.json` presente | ✅ |

**Resultado checklist: 7/7 PASS.** Veredicto UAT final: pendiente del usuario.

## 2. Qué significa "Observabilidad diferida R1.5"

La Remediación 1, tarea **R1.5** (PRD §62, Fase 13) proponía: instrumentar el `paper-runner` con `SetaMetrics` y exponer `/metrics` (formato Prometheus) vía `http.server` de stdlib en `127.0.0.1`, y desplegar `prometheus`/`grafana` del `compose.yaml`.

**Estado real:**
- `SetaMetrics` (`seta_errors_total`, `seta_reconnects_total`, `seta_ws_stale`, `seta_llm_cost_usd`, `seta_latency_seconds`) **existe** (`src/infrastructure/observability/metrics.py`) y `prometheus-client>=0.26.0` **ya es dependencia**.
- Pero `SetaMetrics` solo se instancia en la **API/dashboard** (`interfaces/api/app.py:45` + `/metrics` en `routers/dashboard.py:124`), que **NO corre** en `lenovosrv`.
- El **`paper-runner` (CLI) no está instrumentado** y **no expone `/metrics`**; `ConnectionSupervisor.attempts` es interno y no se emite.
- `prometheus`/`grafana` están definidos en `compose.yaml` pero **no desplegados**.

→ "Diferida" = la instrumentación del runner + despliegue de Prometheus/Grafana no se realizó.

## 3. Métricas durante los 30 días — cobertura real

| Métrica requerida | ¿Medible hoy? | Fuente |
|---|---|---|
| runner health | ✅ | `docker inspect` Status/Health |
| **Bybit WS status/reconnections** | ❌ **FALTA** | sin métrica/log emitido |
| candles processed | ✅ | DB `paper_trade_events` count |
| ATR availability | ✅ (inferible) | fills / ausencia de `stop_unavailable` |
| decision counts BUY/SELL/HOLD | ✅ | DB `action` |
| risk approvals/rejections | ✅ | DB `risk_reason` + `filled` |
| orders/fills | ✅ | DB `filled`, `exec_price`, `quantity` |
| daily_loss triggers | ✅ | DB `risk_reason='max_daily_loss'` |
| stop/TP/trailing exits | ✅ | DB `exit_reason` |
| exceptions | ✅ | `docker logs` |
| portfolio/equity/PnL | ✅ | DB `equity` + cert-state `latest_equity`/`pnl_*` |
| application restarts | ✅ | `docker inspect` RestartCount |

**Demostración (sesión `...-20260906`):** `action=HOLD(37)` · `risk_reason=(aprobado)(37)` · `exit_reason=(ninguno)` · `equity min/max/latest = 1000/1000/1000` · `max_daily_loss=0`.

**Único gap crítico:** **Bybit WS status/reconnections** — el runner no emite nada (logs vacíos).

## 4. Propuesta mínima de observabilidad (PENDIENTE DE GATE)

### Opción A (recomendada — alinea con R1.5, sin dependencias nuevas)
1. Instanciar `SetaMetrics` en `cli/paper_runner.py` (`_run`).
2. Emitir: `set_ws_status(stale=False/True)` en connect/disconnect; `inc_reconnect()` en cada reconexión; `inc_error("ws")` en fallo.
3. Exponer `/metrics` (stdlib `http.server` sobre `generate_latest()`) en `127.0.0.1`.
4. (Opcional) desplegar `prometheus`/`grafana` del `compose.yaml` para scrape + dashboards.

### Opción B (mínima absoluta, sin `/metrics`)
1. Añadir **log estructurado** en connect/reconnect/disconnect del runner (`print("[paper-runner] ws: connected/reconnecting/error")`), medible vía `docker logs`.

Ambas requieren un **commit nuevo + redeploy** (gobernado). Ninguna añade dependencias.

---

**DECISIÓN DEL USUARIO:** ☐ UAT APPROVED + Opción A ☐ UAT APPROVED + Opción B ☐ REJECTED — Fecha/comentario:

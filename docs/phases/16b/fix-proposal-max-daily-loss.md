# Propuesta formal — Corrección de `max_daily_loss` (Fase 16b)

> **Tipo:** bugfix de motor / risk accounting (NO es cambio de estrategia).
> **Estado:** PROPUESTA — pendiente de GATE del usuario. No implementado, no commiteado.
> **Auditoría base:** `docs/phases/16b/` (evidencias) + `/tmp/opencode/audit_*.json`, `demo_reset.py`.

---

## 1. Problema (resumen ejecutivo de la auditoría)

`PaperEngine._realized_pnl_today` es, en realidad, **PnL realizado acumulado de toda la sesión**:
- se inicializa en `0.0` (`paper_engine.py:64`) y solo se incrementa al cerrar posición (`paper_engine.py:184`);
- **nunca se resetea** al cambiar el día (0 referencias a día/fecha en `src/domain/risk/*` y `paper_engine.py`);
- el guard `daily_loss_exceeded` se evalúa **antes de discriminar acción** (`risk/engine.py:71-72`), por lo que bloquea también `HOLD` y `SELL`.

Consecuencia observada en el replay de 36 meses (`BYBIT_ETHBTC_V001`): un único cruce bajo −$20 (2% de $1,000) el 2024-10-09 por un `stop_loss` dejó el trading **bloqueado de forma continua ~683 días** (65,573 ciclos bloqueados: 63,776 HOLD + 1,134 SELL + 663 BUY).

**Clasificación auditoría:** `MULTIPLE_ISSUES` (bug de reset + contabilidad de métrica + evaluación del guard en ciclos sin orden).

---

## 2. Objetivo

1. `max_daily_loss` = pérdida realizada del **día calendario UTC**, con reset a `0` en cada frontera de día.
2. El límite diario impide **nuevas exposiciones** (BUY), pero **no** operaciones reductoras de riesgo.
3. `HOLD` **no** se registra como `rejected order`; el bloqueo se observa en métricas separadas.
4. Mantener `max_drawdown` independiente y **sin tocar sus thresholds**, sizing, EMA/RSI ni reglas de señal.

---

## 3. Diseño propuesto

### 3.1 Abstracción temporal (dominio puro, sin `datetime.now()`)

Nuevo módulo `src/domain/time/day.py`:

```python
MS_PER_DAY = 86_400_000

def utc_day_index(timestamp_ms: int) -> int:
    """Índice de día UTC a partir de epoch-ms (puro, determinista)."""
    return timestamp_ms // MS_PER_DAY
```

- Derivado del **timestamp del evento**, no del reloj de pared.
- Inyectable en `PaperEngine` como `day_key: Callable[[int], int] = utc_day_index` para testabilidad.

### 3.2 Reset diario en `PaperEngine`

En `on_price`, **antes** de `_check_exits` y de evaluar el riesgo (así el cierre que ocurre en el nuevo día imputa al nuevo día):

```python
day = self._day_key(timestamp_ms)
if self._day is None:
    self._day = day
elif day != self._day:
    self._day = day
    self._realized_pnl_today = 0.0
```

- Estado nuevo: `_day: int | None = None`.
- El delta de realized sigue acumulándose solo en `_close_position` (neto: gross − fees − slippage) — **sin cambios** en la fórmula ni en fees/slippage.
- Asunción documentada: timestamps monótonos/ordenados (datos congelados + WS secuencial). Defensa opcional: ignorar retroceso de día (no reset si `day < self._day`).

### 3.3 Reordenamiento de guards en `RiskEngine.evaluate`

Nuevo orden (solo se mueve la comprobación diaria a la rama BUY):

```
kill switch          → bloquea TODO (sin cambio)
max_drawdown         → bloquea TODO (sin cambio; independiente)
HOLD                 → approved no_op (ya no pasa por daily loss)
SELL                 → reduce si hay posición; no_position_to_reduce si no hay (ya no pasa por daily loss)
BUY                  → daily loss → max_open_positions → stop_unavailable → sizing
```

- `daily_loss_exceeded` y `drawdown_exceeded` (guards.py) **no cambian**.
- Los stops/TP/trailing y cierres forzosos ya tienen prioridad absoluta en `_check_exits` (antes de evaluar riesgo) → quedan permitidos automáticamente.

### 3.4 Observabilidad y separación de métricas

`PaperEngine` expone contadores (simples enteros, agregables en reporte/summary):

| Métrica | Semántica | Se incrementa cuando… |
|---|---|---|
| `orders_rejected` | órdenes rechazadas | un BUY/SELL devuelve `approved=False` con `reason` |
| `daily_loss_triggered` | activaciones del guard diario | un **BUY** es rechazado con `reason == "max_daily_loss"` |
| `decision_cycles_blocked` | ciclos bloqueados (observabilidad) | un **HOLD** se procesa estando `daily_loss_active` (realized del día ≤ −límite) |

- `PaperEvent` no registra `risk_reason` para HOLD (el guard diario ya no alcanza HOLD).
- Se añade (si se decide) un flag/propiedad `daily_loss_active: bool` para derivar `decision_cycles_blocked`.
- Los "días con activación" y "activaciones por día" se derivan de los timestamps de los BUY rechazados (el script AFTER lo computa), sin más estado en el motor.

---

## 4. Blast radius (impacto vía codebase-memory-mcp + grep)

| Símbolo | Consumidores (rama `fix/phase-16b-paper-runner-atr`) |
|---|---|
| `RiskEngine.evaluate` | **solo** `PaperEngine.on_price` (`paper_engine.py:124`) |
| `PaperEngine.on_price` | `PaperRunner.handle_kline` (`paper_runner.py:338`) · `paper_session.run_paper_session` (`paper_session.py:105`) |
| `daily_loss_exceeded` | **solo** `RiskEngine.evaluate` (`guards.py:15`) |
| `realized_pnl_today` | interno de `PaperEngine` + tests (`test_paper_engine.py`, `test_risk_engine.py`) |
| Backtest (`backtest_engine.py`) | **NO usa** `PaperEngine`/`RiskEngine` ni `daily_loss` → **fuera de alcance** |

- **Replay y Paper comparten el mismo motor** → la corrección centralizada en `PaperEngine`/`RiskEngine` garantiza paridad temporal (decisión #11) sin cambios en los harness.
- El grafo de codebase-memory cubre `feature/phase-08-llm-decision-agent` (no la rama del fix); se re-indexará y se ejecutará `detect_changes` + `check_index_coverage` tras el commit (regla §4.13).

---

## 5. TDD — tests que deben fallar ANTES de implementar

### 5.1 `tests/test_risk_engine.py` (reordenamiento de guards)

| # | Test (RED) | Expectativa |
|---|---|---|
| R1 | `test_buy_allowed_below_daily_limit` | realized −19.99 → BUY approved |
| R2 | `test_buy_rejected_at_daily_limit` | realized −20.00 → BUY `max_daily_loss` (ya existe; se conserva) |
| R3 | `test_hold_after_daily_limit_is_noop_not_rejected` | HOLD con realized −20 → `approved`, reason `no_op` |
| R4 | `test_sell_with_position_after_daily_limit_reduces` | SELL + posición + realized −20 → `approved` reason `reduce` |
| R5 | `test_sell_without_position_after_daily_limit` | SELL sin posición + realized −20 → `no_position_to_reduce` (NO `max_daily_loss`) |

### 5.2 `tests/test_paper_engine.py` (reset diario + observabilidad)

| # | Test (RED) | Expectativa |
|---|---|---|
| P1 | `test_realized_resets_at_utc_day_boundary` | sembrar realized<0 el día D; evento en D+1 → `realized_pnl_today == 0` |
| P2 | `test_buy_evaluated_again_after_reset` | tras reset, BUY vuelve a aprobarse |
| P3 | `test_open_position_across_midnight_does_not_realize` | posición abierta cruza 00:00 → realized sigue 0 hasta cerrar (sin mark de unrealized) |
| P4 | `test_two_consecutive_days_independent` | pérdida día1 no arrastra al día2; acumuladores independientes |
| P5 | `test_stop_loss_exit_allowed_after_daily_limit` | posición abierta + realized día ya ≤ −20 → exit `stop_loss` `filled=True` |
| P6 | `test_take_profit_and_trailing_allowed_after_daily_limit` | ídem TP/trailing → `filled=True` |
| P7 | `test_hold_after_limit_has_no_risk_reason` | HOLD → `event.risk_reason == ""` y `event.filled is False` |
| P8 | `test_fees_and_slippage_still_included_after_reset` | neto sigue restando fees+slippage tras cruzar día |
| P9 | `test_counters_separated` | `orders_rejected`, `daily_loss_triggered`, `decision_cycles_blocked` toman los valores esperados |

### 5.3 Paridad Replay ↔ Paper

| # | Test (RED) | Expectativa |
|---|---|---|
| X1 | `test_replay_and_paper_share_daily_reset_semantics` | misma secuencia de velas con cruce de medianoche por `paper_session` y por `PaperRunner` (FakeStream/Repo) → mismo punto de reset, mismo `realized_pnl_today` por vela |

- Cobertura objetivo: **≈100% branch** en `RiskEngine.evaluate`, `PaperEngine` (nueva lógica de día) y `utc_day_index`.

---

## 6. Archivos a tocar (plan de implementación, tras GATE)

- **MODIFICAR** `src/domain/risk/engine.py` — reordenar guard diario a rama BUY.
- **MODIFICAR** `src/application/services/paper_engine.py` — `_day`/reset/contadores (+ posible flag `daily_loss_active`).
- **CREAR** `src/domain/time/day.py` — `utc_day_index` (dominio puro).
- **MODIFICAR** `src/version.py` — bump `__version__` `0.1.0 → 0.1.1` (bugfix).
- **MODIFICAR** tests `test_risk_engine.py`, `test_paper_engine.py`; **CREAR** `tests/test_daily_loss_reset.py` (P1–P9) y extender `test_cli_paper_runner.py` (X1).
- **Sin cambios:** `RiskConfig` (thresholds/sizing intactos → `risk-v1` se conserva), `strategy.py` (`baseline-v1`), `guards.py`, `portfolio.py`, `fees/slippage`.

---

## 7. Verificación AFTER (re-ejecución exacta)

Con el **mismo** dataset/confs:

```
dataset BYBIT_ETHBTC_V001 · ETHUSDT 15m · 2023-09-08 → 2026-08-23
baseline-v1 · risk-v1 · capital 1000 · fees 10bps · slippage 2bps
```

Dos salidas:
1. **`python -m main paper-session`** (oficial, verifica SHA-256, determinista) → métricas estándar.
2. **Replay instrumentado** (reutiliza la auditoría) → desglose de señales/rechazos/bloqueos.

Comparar **BEFORE vs AFTER** con:

- BUY signals · BUY approved · BUY rejected por motivo (`max_daily_loss`, `max_open_positions`, `stop_unavailable`, `zero_size`, `max_drawdown`) · fills · trades cerrados · días con `max_daily_loss` activado · nº activaciones diarias · blocked cycles · Net PnL · Profit Factor · Sharpe · Sortino · Max Drawdown · Expectancy · fees · slippage · equity final.
- **Aserto de cierre:** en AFTER **no existe** período de bloqueo continuo post-trigger (cada día afectado es independiente; `blocked_cycles` solo dentro del día que dispara; `day_open_blocked_sin_trigger_del_día = 0`).

---

## 8. Gobierno y registro

- **Clasificación:** bugfix motor/risk accounting (no estrategia). Thresholds/sizing/EMA-RSI/reglas de señal intactos.
- **Versionado:** `strategy_version = baseline-v1` (sin cambio) · `RiskConfig.version = risk-v1` (sin cambio de thresholds) · `__version__ = 0.1.1` (nuevo).
- **Registro requerido en el reporte:** `git_commit` del fix · evidencia de la auditoría (`docs/phases/16b/evidence/`) · tests antes/después · `git diff` · impacto `codebase-memory-mcp` (`detect_changes` + `check_index_coverage` + re-index).
- **Gate:** `harness/scripts/gate_check.py --phase 16b` + Commit Candidate Report → esperar **GATE del usuario** antes de commitear. No se hace commit, push, merge ni redeploy sin autorización.

---

## 9. Decisiones a confirmar por el usuario (GATE)

1. Semántica diaria = **día calendario UTC** (frontera 00:00 UTC) — confirma.
2. ¿El guard diario debe evaluarse únicamente sobre **BUY** (SELL/cierre siempre permitidos), como se propone?
3. Observabilidad: mantener 3 contadores (`orders_rejected`, `daily_loss_triggered`, `decision_cycles_blocked`) en el motor + exponer en reporte periódico, ¿suficiente? (sin tocar SetaMetrics ahora).
4. `RiskConfig.version` se **conserva** `risk-v1` (solo cambia el comportamiento, no los parámetros); el cambio se registra vía `__version__` + `git_commit`. ¿De acuerdo?

---

**DECISIÓN DEL USUARIO:** ☐ GATE APPROVED → implementar TDD ☐ REJECTED / cambios — Fecha/comentario:

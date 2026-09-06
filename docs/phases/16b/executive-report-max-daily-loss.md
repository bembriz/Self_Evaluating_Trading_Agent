# Reporte Ejecutivo — Corrección de `max_daily_loss` + slippage (Fase 16b)

> **Tipo:** bugfix de motor / risk accounting (NO cambio de estrategia).
> **Estado:** implementado vía TDD (bug #1 y #2) · **pendiente de GATE de commit** · sin commit/push/redeploy.
> **Rama:** `fix/phase-16b-paper-runner-atr` · **App:** `0.1.0 → 0.1.1` · **Strategy:** `baseline-v1` · **RiskConfig:** `risk-v1` (sin cambios de parámetros).

---

## 1. Executive Summary

El replay oficial de 36 meses (`BYBIT_ETHBTC_V001`, ETHUSDT 15m, 103,680 velas) reportó **65,573 eventos `max_daily_loss`**. La auditoría demostró que ese total **mezclaba órdenes reales con ciclos HOLD**:

- **63,776 (97.3%)** ciclos `HOLD` sin orden candidata (ruido de observabilidad).
- **1,134 (1.7%)** `SELL` sin posición (órdenes reductoras de riesgo).
- **663 (1.0%)** **BUY rechazados** (órdenes reales de nueva exposición).

Dos bugs corregidos vía TDD:

1. **Bug #1 — `max_daily_loss` sin reset diario:** `_realized_pnl_today` acumulaba PnL de toda la sesión; un único cruce bajo −$20 (2024-10-09) bloqueó el trading ~683 días. Fix: reset diario UTC + guard solo sobre BUY. Resultado: **0 bloqueos**, las 1,055 señales BUY ejecutan.
2. **Bug #2 — slippage doble contabilizada:** la slippage estaba embebida en `exec_price` y además se restaba de nuevo en `net_pnl`. Fix (Opción A): `net_pnl = gross − fees`; la slippage se conserva como métrica analítica. Resultado: **reconciliación residual = 0**.

Con ambos fixes, la baseline revela su resultado real: **neto-negativa** tras costos (Net PnL −$43.26, Profit Factor 0.68, Expectancy −$0.041).

---

## 2. Clasificación

```
MULTIPLE_ISSUES:
  BUG #1 → max_daily_loss sin reset diario (CORREGIDO)
  BUG #2 → slippage contabilizada dos veces (CORREGIDO, Opción A)
  METRIC_ACCOUNTING_ISSUE → 65,573 ≠ órdenes rechazadas (663 BUY + 1,134 SELL + 63,776 HOLD)
```

---

## 3. Bug #1 — root cause y fix (corregido)

**Root cause:** `PaperEngine._realized_pnl_today` solo se inicializaba en `0.0` y crecía en `_close_position`; **sin reset por día**. `RiskEngine.evaluate` comprobaba `daily_loss` antes de discriminar acción.

**Fix:**
1. `src/domain/time/day.py` — `utc_day_index(ts) = ts // 86_400_000` (puro, sin `datetime.now()`).
2. `PaperEngine.on_price` — reset `_realized_pnl_today = 0.0` en cada frontera UTC (antes de exits).
3. `RiskEngine.evaluate` — `kill → drawdown → HOLD → SELL → BUY(daily+max_positions+stop+sizing)`.
4. `OutOfOrderTimestampError` si `timestamp_ms < último` (sin mutar estado).
5. Métricas separadas: `orders_rejected` · `daily_loss_triggered` · `daily_loss_active_cycles`.

---

## 4. Bug #2 — root cause y fix (corregido, Opción A)

**Root cause:** `exec_price` ya incluye slippage (`price×(1±rate)`), por lo que el cash y `gross_pnl` ya la contienen; pero `Portfolio.apply_sell` (`portfolio.py:76`) y `compute_metrics` (`metrics.py:53`) la volvían a restar: `net_pnl = gross_pnl − fees − slippage`. Resultado: `realized_pnl`/`Net PnL` sobre-declaraban pérdida en `+total_slippage`, mientras `equity` (cash) era correcto.

**Fix (Opción A):** mantener slippage en `exec_price`; eliminar la resta redundante → `net_pnl = gross_pnl − fees`. La slippage se sigue calculando y persistiendo como métrica analítica (`Trade.slippage`, `PerformanceMetrics.slippage`), sin re-descontarse de PnL ni de cash.

---

## 5. TDD (RED → GREEN)

**Bug #1 — RED:** 3 fallos RiskEngine (HOLD/SELL tras límite devolvían `max_daily_loss`) + import ausente. **GREEN:** `tests/test_daily_loss_reset.py` (13) + 4 en `test_risk_engine.py`.

**Bug #2 — RED:** 8 fallos (round-trip manual, residual, slippage/fees una vez, compute_metrics, y 3 tests de `test_metrics`/`test_portfolio` actualizados). **GREEN:** `tests/test_pnl_reconciliation.py` (9 tests) + `test_metrics.py` y `test_portfolio.py` corregidos.

**Checks:** suite completa `tests/` (unit + integration) **489 passed, 1 skipped** · cobertura global **94.62% (branch 95%)** · integration **PASS (16)** · `ruff check`/`format` limpios · `mypy` sin issues (207 ficheros).

---

## 6. Reconciliación contable (bug #2)

Balance: `final_equity = initial_cash + realized_net_pnl + unrealized_pnl` (residual = 0 esperado).

### 6.1 Reconciliación — mismo comportamiento (fix #1 aplicado), antes/después del fix #2

| Partida | ANTES fix#2 | DESPUÉS fix#2 |
|---|---|---|
| initial_cash | 1,000.000000 | 1,000.000000 |
| final_cash | 956.741005 | 956.741005 |
| final_position_qty | 0.0 | 0.0 |
| final_position_value | 0.0 | 0.0 |
| realized_gross_pnl | −1.051607 | −1.051607 |
| fees | 42.207388 | 42.207388 |
| analytical_slippage_cost | 8.441478 | 8.441478 |
| realized_net_pnl | −51.700473 | **−43.258995** |
| unrealized_pnl | 0.0 | 0.0 |
| final_equity | 956.741005 | 956.741005 |
| **reconciliation_residual** | **+8.441478** | **0.0** |

> Antes: `net = gross − fees − slippage` → residual = +slippage (8.441478). Después: `net = gross − fees` → residual = 0. `final_equity` idéntico en ambos (el cash nunca estuvo mal), solo cambia el PnL reportado.

### 6.2 Reconciliación final (fix #1 + #2) — evidencia

`docs/phases/16b/evidence/reconciliation-AFTER.json`:

```json
initial_cash=1000.0 · final_cash=956.741005 · final_position_qty=0.0
realized_gross_pnl=-1.051607 · fees=42.207388 · analytical_slippage_cost=8.441478
realized_net_pnl=-43.258995 · unrealized_pnl=0.0 · final_equity=956.741005
reconciliation_residual=0.0
```

---

## 7. BEFORE vs AFTER (36 meses, ETHUSDT 15m) — fix #1

| Métrica | BEFORE (bug #1) | AFTER (fix #1) |
|---|---|---|
| BUY signals | 1,055 | 1,055 |
| BUY approved | 392 | **1,055** |
| BUY rejected (`max_daily_loss`) | 663 | **0** |
| Fills | 784 | 2,110 |
| Trades cerrados | 392 | 1,055 |
| Días con trigger diario | 471 | **0** |
| Activaciones diarias (total / máx) | 663 / 5 | 0 / 0 |
| Blocked cycles | 63,776 | **0** |
| Días bloqueados / spillover | 684 / 213 | **0 / 0** |
| Gross PnL (sobre exec_price) | −$1.40 | −$1.05 |
| fees | $15.68 | $42.21 |
| analytical slippage | $3.14 | $8.44 |
| **Net PnL (corregido = gross − fees)** | **−$17.08** | **−$43.26** |
| Equity final | $982.92 | $956.74 |
| Profit Factor | 0.581 | 0.680 |
| Sharpe / Sortino | −2.19 / −3.23 | −2.90 / −4.31 |
| Max Drawdown | 1.76% | 4.38% |
| Expectancy (por trade, net) | −$0.0516 | −$0.0410 |

> En BEFORE el `Net PnL` correcto es −$17.08 (= equity − initial); el −$20.22 previo incluía el doble conteo de slippage. En AFTER, −$43.26 = gross − fees.

---

## 8. Gobierno

- **Sin cambios de estrategia/thresholds/sizing/fee model/slippage rate/reglas de señal.**
- `strategy_version = baseline-v1` · `risk_config_version = risk-v1` · `application_version = 0.1.1` (ambos bugfixes en la misma versión, root causes documentados por separado).
- Registro requerido en Commit Candidate: `git_commit`, evidencia (`reconciliation-{AFTER,BEFORE}.json`, `replay-36m-{AFTER-fixed,BEFORE}.json`), tests antes/después, `git diff`, impacto `codebase-memory-mcp`.
- **No** se ha hecho commit, push, merge ni redeploy.

---

## 9. Próximos pasos (tras GATE)

1. Re-indexar grafo + `detect_changes`/`check_index_coverage` (regla §4.13).
2. Commit Candidate Report → GATE de commit.
3. (Después) redeploy `lenovosrv` (misma `strategy_version`, nueva `application_version`) + UAT 16b.

---

**DECISIÓN DEL USUARIO:** ☐ GATE APPROVED → preparar commit ☐ REJECTED / cambios — Fecha/comentario:

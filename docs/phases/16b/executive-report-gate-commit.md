# Reporte Ejecutivo — Pre-commit Gate (Fase 16b: max_daily_loss + slippage)

> **Estado:** PRE-COMMIT COMPLETO · **pendiente de GATE de commit** · sin commit/push/merge/tag/redeploy.
> **Rama:** `fix/phase-16b-paper-runner-atr` · **App:** `0.1.1` · **Strategy:** `baseline-v1` · **RiskConfig:** `risk-v1` (sin cambios).

---

## 1. E2E automatizados (aplicables a ambos fixes)

Nuevo `tests/e2e/test_e2e_fixes.py` (motor real `PaperEngine`, sin mock del motor). **PASS (2)**.

### E2E-1 — `max_daily_loss`
Flujo completo verificado:
```
BUY fills → stop-loss exit (realiza pérdida, activa daily_loss) →
BUY blocked (max_daily_loss) → HOLD allowed (sin risk_reason) →
SELL allowed (no_position_to_reduce, NO max_daily_loss) →
UTC rollover → reset (realized=0, daily_loss_active=False) → BUY allowed (fills)
```

### E2E-2 — Contabilidad / reconciliación
```
BUY (execution con slippage embebida en exec_price) → SELL →
fees > 0 · slippage (analítica) > 0 → portfolio → metrics (net_pnl == realized) →
final_equity = initial + realized → reconciliation residual = 0
```

> Replay determinista de 36 meses = **E2E adicional automatizado** (2 corridas byte-idénticas; evidencia en `docs/phases/16b/evidence/replay-36m-AFTER-fixed.json` y `reconciliation-AFTER.json`).

---

## 2. Test skipped (justificado)

`tests/test_fastembed_provider.py:97` — smoke del modelo de embeddings real que exige `RUN_MODEL_SMOKE=1` (descarga/ejecuta el modelo local, opt-in por coste/tiempo). **No guarda relación con los fixes** de risk accounting ni representa cobertura pendiente de este cambio.

---

## 3. `detect_changes` ejecutado pre-commit (codebase-memory-mcp)

- `detect_changes` (base `main` → `HEAD` `b47ff28`): `changed_files=410`, `impacted_total=127`, `seed_symbols=2833`.
- Módulos impactados: `src/interfaces 12` · `src/application 6` · `src/domain 5` · `src/infrastructure 5` · `harness/scripts 2` · `harness/tests 4` · `migrations 1`.
- **Nota de alcance:** `detect_changes` opera sobre diffs commiteados; como el WIP no está commiteado, este resultado refleja la rama vs `main`. El blast radius **preciso del WIP** se obtuvo con `trace_path` (inbound) sobre los símbolos modificados:

| Símbolo | Consumidores |
|---|---|
| `RiskEngine.evaluate` | `PaperEngine.on_price` (+ runner/paper_session transitivos) |
| `PaperEngine.on_price` | `PaperRunner.handle_kline`, `cli.paper_runner`, `paper_session`, `main` |
| `Portfolio.apply_sell` | `PaperEngine`, `ml_pipeline`, `buy_hold`, `backtest`, `paper_session` |
| `compute_metrics` | `paper_session`, `backtest`, `buy_hold`, `ml_pipeline` |

- Re-index + `detect_changes` final se ejecutarán **inmediatamente tras el commit** (regla §4.13).

**Incorporado al Commit Candidate Report** (`docs/phases/16b/commit-candidate-002.md`).

---

## 4. Resumen final de gates

| Gate | Resultado |
|---|---|
| Unit tests | PASS |
| Integration tests (PostgreSQL 5433) | **PASS (16)** |
| E2E (E2E-1 + E2E-2) | **PASS (2)** |
| Suite completa | **491 passed, 1 skipped** |
| Cobertura global (unit+integration) | **94.62%** (branch **95%**) |
| Branch críticos (RiskEngine/guards/portfolio/metrics/day) | **100%** · paper_engine **98%** |
| Ruff check / format | clean (235 ficheros) |
| Mypy | 0 issues (208 ficheros) |
| Replay 36m determinista | 2 corridas byte-idénticas |
| Reconciliación contable | residual **0.0** |
| Reset UTC / SELL-stop-TP / out-of-order | `test_daily_loss_reset.py` PASS |
| `detect_changes` + `check_index_coverage` | ejecutados pre-commit · cobertura limpia |
| Git diff / secret scan | 9 modificados + 3 nuevos · **sin secretos** |

### Benchmark oficial corregido `baseline-v1`

BUY signals **1,055** · Trades **1,055** · Net PnL **−$43.26** · Final equity **$956.74** · Profit Factor **0.680** · Expectancy **−$0.0410** · Max Drawdown **4.38%**.

> **`baseline-v1` no demuestra edge económico y no es candidata a LIVE.**

---

## 5. Versiones mantenidas

- `strategy_version = baseline-v1` (sin cambio)
- `risk_config_version = risk-v1` (sin cambio de parámetros)
- `application_version = 0.1.1` (ambos bugfixes en la misma versión)

---

**DECISIÓN DEL USUARIO:** ☐ GATE APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

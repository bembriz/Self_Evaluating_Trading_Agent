# M9-B2 — Full DEVELOPMENT run: OLD (close-only) vs NEW (trade-sequence)

**Fecha:** 2026-09-29 (UTC-6) · **Rama:** `medalion` @ `fcba380e423ee717fe6ffd1244f14ffb072c40b2`
**Ejecución:** lenovosrv, runner `harness/scripts/m9b_common_window.py` (HEAD), secuencial (sin paralelismo).
**Alcance:** comparación **in-sample / DEVELOPMENT** sobre los mismos 647 días. **NO** hay
lectura walk-forward ni holdout. **NO** se declara rentabilidad futura ni viabilidad OOS.

## 1. Dataset y ventana

| Campo | Valor |
|---|---|
| dataset_id | `gold-replay-5ca68f44c37d2321f56a10ecbc08bc0584d70c17826f07604dbba77a8b71134a` |
| manifest sha256 | `c095d5740d9ca0c414ac0b11049008aa716262870edbeadc344dbb16188eb62e` |
| split | `DEVELOPMENT` · ordering_fidelity `PARTIAL` |
| dates | 2023-09-09 .. 2025-06-16 (**647**) |
| ventana UTC | `[2023-09-09T00:00:00Z, 2025-06-17T00:00:00Z)` |
| velas 15m | **62112** (647 × 96), contiguas y exactas (guard `--expect-common-window`) |
| marker | `/srv/data/.lenovosrv-data-volume` = `LENOVO_DATA` (válido) |
| code_git_sha | `fcba380e423ee717fe6ffd1244f14ffb072c40b2` |

## 2. Ejecución (6 corridas, sequencial)

| # | Strategy / Model | rc | duración | decisión | fills | rejected |
|---|---|---|---|---|---|---|
| 1 | baseline / old_close_only | 0 | 14 s | BUY 631 · HOLD 59984 · SELL 1497 | 1262 | — |
| 2 | baseline / trade_sequence | 0 | 2093 s | BUY 631 · HOLD 60461 · SELL 1020 | 691 | 0 |
| 3 | donchian / old_close_only | 0 | 14 s | BUY 1893 · HOLD 55847 · SELL 4372 | 1678 | — |
| 4 | donchian / trade_sequence | 0 | 2122 s | BUY 2034 · HOLD 56078 · SELL 4000 | 1108 | 0 |
| 5 | bollinger / old_close_only | 0 | 21 s | BUY 457 · HOLD 29406 · SELL 32249 | 782 | — |
| 6 | bollinger / trade_sequence | 0 | 2104 s | BUY 457 · HOLD 29521 · SELL 32134 | 651 | 0 |

- `DRIVER_FAIL=0`; todos `rc=0`; **sin `.part`**; NEW procesa ~424.1M trades Silver por corrida
  (streaming, sin materializar la lista).
- `decisions_rejected=0` en las 3 corridas NEW (el RiskEngine dinámico no rechazó ninguna
  apertura en la ventana).
- La paridad exigida es la **secuencia lógica** de señales, no el conteo de eventos (OLD cuenta
  eventos PaperEngine; NEW cuenta señales del provider).

## 3. Paridad OLD / NEW (FAIL CLOSED si difiere)

| Estrategia | signal_hash OLD == NEW | candle_hash OLD == NEW | PARITY |
|---|---|---|---|
| baseline | ✅ `62bd216853b5…` | ✅ `fa8964741259…` | **PASS** |
| donchian | ✅ `56252806aa91…` | ✅ `fa8964741259…` | **PASS** |
| bollinger | ✅ `72c8f90bcc0d…` | ✅ `fa8964741259…` | **PASS** |

## 4. Métricas económicas OLD vs NEW (misma definición)

`MAX_DRAWDOWN_BASIS=REALIZED_CLOSED_TRADES` · `profit_factor` sobre net realizado
(`None` si no hay pérdidas) · `final_equity = capital + net realizado` (REALIZED-ONLY) ·
capital inicial 1000.

### baseline

| Métrica | OLD | NEW | Δ (NEW−OLD) |
|---|---|---|---|
| closed_trades | 631 | 631 | 0 |
| gross_reference_pnl | 7.483990 | 5.546201 | −1.937789 |
| gross_execution_pnl | 2.434493 | 0.381319 | −2.053174 |
| fees | 25.247482 | 25.245456 | −0.002026 |
| slippage | 5.049497 | 5.049091 | −0.000406 |
| **net_pnl** | **−22.812989** | **−24.864136** | **−2.051147** |
| expectancy | −0.036154 | −0.039404 | −0.003250 |
| profit_factor | 0.7230 | 0.6242 | −0.0988 |
| win_rate | 0.3043 | 0.2821 | −0.0222 |
| max_drawdown_abs | 26.447965 | 25.389464 | −1.058501 |
| max_drawdown_pct | 0.026432 | 0.025389 | −0.001043 |
| average_holding_ms | 16 995 879.6 | 11 277 030.1 | −5 718 849.5 |
| final_equity | 977.187011 | 975.135864 | −2.051147 |

Extractos `summary_sha256` / `trade_ledger_sha256`: OLD `24ce973e…` / `f2bed06d…` ·
NEW `5ed56f1a…` / `ef1f85a4…`.

### donchian

| Métrica | OLD | NEW | Δ (NEW−OLD) |
|---|---|---|---|
| closed_trades | 839 | 987 | +148 |
| gross_reference_pnl | 12.545463 | 8.909108 | −3.636355 |
| gross_execution_pnl | 5.830954 | 0.711582 | −5.119372 |
| fees | 33.572543 | 39.488758 | +5.916215 |
| slippage | 6.714509 | 7.897752 | +1.183243 |
| **net_pnl** | **−27.741589** | **−38.777176** | **−11.035587** |
| expectancy | −0.033065 | −0.039288 | −0.006223 |
| profit_factor | 0.7478 | 0.6573 | −0.0905 |
| win_rate | 0.3027 | 0.2796 | −0.0231 |
| max_drawdown_abs | 29.919263 | 41.969591 | +12.050328 |
| max_drawdown_pct | 0.029900 | 0.041965 | +0.012065 |
| average_holding_ms | 15 175 566.2 | 10 586 978.5 | −4 588 587.7 |
| final_equity | 972.258411 | 961.222824 | −11.035587 |

Extractos `summary_sha256` / `trade_ledger_sha256`: OLD `e4f5155b…` / `78439057…` ·
NEW `e35ef3fa…` / `4325b989…`.

### bollinger

| Métrica | OLD | NEW | Δ (NEW−OLD) |
|---|---|---|---|
| closed_trades | 391 | 405 | +14 |
| gross_reference_pnl | 1.833609 | 1.263319 | −0.570290 |
| gross_execution_pnl | −1.294758 | −1.982729 | −0.687971 |
| fees | 15.641833 | 16.201230 | +0.559397 |
| slippage | 3.128367 | 3.240246 | +0.111879 |
| **net_pnl** | **−16.936591** | **−18.183960** | **−1.247369** |
| expectancy | −0.043316 | −0.044899 | −0.001583 |
| profit_factor | 0.4307 | 0.4184 | −0.0123 |
| win_rate | 0.4629 | 0.4469 | −0.0160 |
| max_drawdown_abs | 16.936591 | 18.183960 | +1.247369 |
| max_drawdown_pct | 0.016937 | 0.018184 | +0.001247 |
| average_holding_ms | 6 267 774.9 | 5 171 540.5 | −1 096 234.4 |
| final_equity | 983.063409 | 981.816040 | −1.247369 |

Extractos `summary_sha256` / `trade_ledger_sha256`: OLD `8776aa19…` / `70126f8e…` ·
NEW `20120eac…` / `406f5209…`.

### Conteo de exit reasons

| Estrategia / Modelo | stop_loss | take_profit | trailing_stop | strategy_exit | llm_sell (raw OLD) |
|---|---|---|---|---|---|
| baseline OLD | 322 | 155 | 62 | — | 92 |
| baseline NEW | 362 | 131 | 78 | 60 | — |
| donchian OLD | 325 | 199 | 36 | — | 279 |
| donchian NEW | 556 | 215 | 95 | 121 | — |
| bollinger OLD | 115 | 2 | 0 | — | 274 |
| bollinger NEW | 155 | 4 | 0 | 246 | — |

## 5. Comparabilidad

- **`POPULATIONS_DIRECTLY_COMPARABLE=NO`**: cambian fills (un reloj vs dos relojes),
  duración, reentradas, subtipo de salida (intrabar vs cierre de vela) y, en donchian,
  también el número de decisiones BUY (1893 vs 2034).
- **`Phase21R` (baseline 634 / donchian 1086 / bollinger 460)**:
  `REFERENCE_ONLY_DIFFERENT_BOUNDARY_WINDOW=YES` — otra fuente/ventana; no es una población
  comparable.
- Resultados **DEVELOPMENT / in-sample**: no demuestran rentabilidad futura ni viabilidad
  out-of-sample. Net negativo en las 6 combinaciones; fees+slippage dominan el neto.

## 6. Safety

`WALK_FORWARD_READS=0` · `FINAL_HOLDOUT_READS=0` · `PAPER_CONTAINER_CHANGED=NO` ·
`CERTIFICATION_TOUCHED=NO` · `progress.yaml` sin cambios · `src/domain/risk/` y `PaperEngine`
intactos (runner en HEAD, `src/**` no cambió) · Silver/Gold sin `.part` ·
`LEGACY_M7_LEDGER_IDENTICAL=YES` (`6d64b62b…`).

## 7. Evidencia (`docs/phases/23/evidence/`)

| Artefacto | Contenido |
|---|---|
| `m9b-full-01-run.log` | driver secuencial + `status.tsv` + `DRIVER_DONE` |
| `m9b-full-02-metrics.log` | extracción compacta de los 6 summaries + paridad |
| `m9b-full-03-verify.log` | dataset/ventana, código==HEAD, 6+6 artefactos, `.part=0`, legacy, paper, holdout |
| `m9b-full-<strategy>-<model>.log` | stdout del runner por combinación (6) |
| `log.md` | índice de evidencias |

Artefactos en lenovosrv: `/srv/fast/medallion/m9b-full/{summary.json,trades.jsonl}` (6+6).

---

## SALIDA

```text
M9B_FULL_DEVELOPMENT=PASS
WINDOW_DAYS=647
CANDLES_15M=62112

BASELINE_PARITY=PASS
DONCHIAN_PARITY=PASS
BOLLINGER_PARITY=PASS

BASELINE_OLD_NET=-22.812989
BASELINE_NEW_NET=-24.864136

DONCHIAN_OLD_NET=-27.741589
DONCHIAN_NEW_NET=-38.777176

BOLLINGER_OLD_NET=-16.936591
BOLLINGER_NEW_NET=-18.183960

ARTIFACTS_COMPLETE=YES
LEGACY_M7_LEDGER_IDENTICAL=YES

WALK_FORWARD_READS=0
FINAL_HOLDOUT_READS=0
PAPER_CONTAINER_CHANGED=NO
CERTIFICATION_TOUCHED=NO

READY_FOR_M9B_REVIEW=YES
```

# M9-B2A — Common Window Runner (OLD vs NEW) + corrección Trailing ATR

**Fecha:** 2026-09-29 (UTC-6)
**Rama:** `medalion` @ `841c6369f771646006097b545c03965be45094c4` (cambios en worktree, **sin commit**)
**Objetivo:** preparar el runner reproducible OLD-vs-NEW para la comparación de 647 días y
corregir la diferencia semántica del trailing ATR antes de la corrida larga.
**Estado:** runner listo + corrección validada + smoke 3 días OLD×3/NEW×3. **NO** se ejecutó
la corrida de 647 días (gate posterior). Sin commit/push/mark-done.

## 1. Ventana común

| Campo | Valor |
|---|---|
| START (inclusive) | `2023-09-09T00:00:00Z` |
| END_EXCLUSIVE | `2025-06-17T00:00:00Z` |
| Días | **647** |
| Velas 15m esperadas | **62112** (647 × 96) |
| Fuente de velas | **Medallion Silver → Gold 15m** (idéntica para OLD y NEW) |
| Fuente prohibida | `BYBIT_ETHBTC_V001` (solo referencia externa) |

Resultados Phase 21R (`baseline=634`, `donchian=1086`, `bollinger=460`) son
**REFERENCE_ONLY**, no una población comparable.

`slice_window()` exige conteo exacto y contigüidad 15m (FAIL CLOSED). El flag
`--expect-common-window` fuerza START/END/647/62112 exactos — verificado en host con el
dataset de 3 días → **FAIL CLOSED** (`m9b2a-07` §2).

## 2. Modelos (mismos parámetros 22B)

| | OLD `old_close_only` | NEW `trade_sequence` |
|---|---|---|
| Motor | `PaperEngine` (semántica close-only previa) | Trade-Level Replay M7 (`TRADE_SEQUENCE_TAKER_PROXY`) |
| Precio | `candle.close` | fills sobre trades históricos de Silver |
| ATR | ATR 15m de la vela confirmada | idem (Decision.atr) |
| Riesgo | `RiskEngine` dinámico | `RiskEngine` dinámico |
| stop / target / trailing | 2 ATR / 2 R / 3 ATR | idem |
| Fee / slippage / intensity | 10 bps / 2 bps / MEDIUM | idem |
| RiskConfig | `risk-v2-atr-exit` (`m9b-common-window-v1`) | idem |

## 3. Corrección aprobada — Trailing ATR en `sizing_mode=risk_engine`

- **entry ATR**: `Decision.atr` (sin cambios) → `initial_stop`/`initial_target` siguen
  congelados desde `reference_price`.
- **trailing ATR**: pasa a ser el **último ATR 15m confirmado**, actualizado únicamente
  cuando una vela queda confirmada (`close_time <= cutoff`) en `_advance`; entre cierres se
  conserva el último ATR confirmado y nunca se usa ATR de vela futura/incompleta.
- **Orden M7 intacto**: `_risk_eval` actualiza path → evalúa protective → target → recién
  entonces eleva el trailing; el mismo trade no puede elevar el trailing y ser detenido por
  él.
- **fixed legacy intacto**: en `fixed` el trailing sigue usando el ATR de entrada y el
  ledger M7 sigue byte-idéntico.

## 4. Normalización de exit reason (solo presentación)

`llm_sell → strategy_exit` (mapa `EXIT_REASON_PRESENTATION`), conservando el **raw** en el
reporte. **PaperEngine no se altera** — verificado en el smoke de bollinger OLD:
`exit_raw={"llm_sell":3,"stop_loss":1}` → `exit_presentation={"stop_loss":1,"strategy_exit":3}`.

## 5. Runner versionado

`harness/scripts/m9b_common_window.py` (nuevo):
`--strategy {baseline,donchian,bollinger}` · `--model {old_close_only,trade_sequence}` ·
`--start/--end-exclusive` · `--expect-common-window` · `--require-marker`.
Imprime `WINDOW`, `DATASET`, `MODEL`+`candle_hash`, `PARITY` (`signal_hash` vs esperado),
`SUMMARY` (decisions/fills/exit raw+presentación/equity) y `REPORT_SHA256` determinista.
Paridad de señales **obligatoria** antes de interpretar PnL: si `signal_hash` difiere →
`PARITY_FAILED` y exit 1 (FAIL CLOSED).

## 6. Tests añadidos

`tests/test_trade_replay.py` (+5, sección M9-B2): trailing usa el último ATR confirmado
(≠ ATR de entrada), initial stop/target con ATR de entrada, conserva el ATR entre velas
(trade intra-intervalo), no-lookahead (corrupción de velas futuras no cambia el registro),
`fixed` usa ATR de entrada (legacy).

`harness/tests/test_m9b_common_window.py` (+10): ventana 647/62112, math 3 días, conteo y
contigüidad, mapeo de exit reasons, misma fuente de velas y paridad OLD==NEW, FAIL CLOSED de
paridad, causalidad de señales, determinismo OLD/NEW, parámetros 22B.

## 7. Evidencia (`docs/phases/23/evidence/`)

| Paso | Artefacto | Resultado |
|---|---|---|
| 01 calidad | `m9b2a-01-quality.log` | **PASS** — ruff + format + mypy (290 archivos) |
| 02 suite global | `m9b2a-02-tests-global.log` | **PASS** — 1263 passed, 1 skipped · cobertura **90.56%** |
| 03 scope medallion | `m9b2a-03-tests-medallion.log` | **PASS** — 323 passed · **94.27%** |
| 04 harness tests | `m9b2a-04/04b/04d` | **PASS** — 77 passed (2 fallos PDF pre-existentes, excluidos); módulo nuevo **69%** (CLI/IO validados en smoke) |
| 05 deploy | `m9b2a-05/05b/05c-deploy.log` | **PASS** — runner importable; parámetros 22B y map de exit reasons verificados |
| 06 smoke | `m9b2a-06/06b/06c-smoke.log` | **PASS** — OLD×3 y NEW×3, RUN1==RUN2 byte-a-byte, `PARITY PASS` en las 3 |
| 07 verify | `m9b2a-07-verify.log` | **PASS** — legacy sha `6d64b62b…` idéntico y canónico intacto; guard de ventana FAIL CLOSED; paridad + candle_hash iguales; sin `.part`; paper sin cambios; WF/holdout 0 |
| 08 secret scan | `m9b2a-08-secret-scan.log` | **PASS** — 6 patrones HITS=0; 0 hex-64 en código/tests |

## 8. Smoke 3 días (Gold `gold-replay-a8c49e0b…`, 2024-06-01/02/03, 288 velas)

| Estrategia | Modelo | decisions | fills | exits (raw→presentación) | equity_final | determinista |
|---|---|---|---|---|---|---|
| baseline | OLD | BUY 1 / HOLD 284 / SELL 3 | 2 | stop_loss 1 | 999.9428 | ✅ |
| baseline | NEW | BUY 1 / HOLD 285 / SELL 2 | 1 | trailing_stop 1 | 999.9733 | ✅ |
| donchian | OLD | BUY 3 / HOLD 266 / SELL 19 | 4 | stop_loss 1, take_profit 1 | 1000.0243 | ✅ |
| donchian | NEW | BUY 4 / HOLD 266 / SELL 18 | 3 | stop_loss 3 | 999.6747 | ✅ |
| bollinger | OLD | BUY 5 / HOLD 138 / SELL 145 | 9 | llm_sell 3 → strategy_exit 3, stop_loss 1 | 999.7997 | ✅ |
| bollinger | NEW | BUY 5 / HOLD 139 / SELL 144 | 6 | stop_loss 2, strategy_exit 2 | 999.7351 | ✅ |

- **Paridad de señales** OLD==NEW por estrategia: `baseline 059f2d64…`, `donchian 91356974…`,
  `bollinger 3141b4a5…`; `candle_hash` idéntico en ambos modelos
  `3443d340cd8af36b2ac4c8a0a94168db6ba705a4a399edac8246ab46bc2eec57`.
- Los contadores `decisions` son **específicos de cada modelo** (OLD cuenta eventos
  PaperEngine; NEW cuenta señales del provider): la paridad exigida es la **secuencia
  lógica** de señales (hash), no el conteo de eventos.
- **Sin conclusiones económicas**: smoke de mecanismo sobre 3 días.

## 9. Safety

`WALK_FORWARD_READS=0` · `FINAL_HOLDOUT_READS=0` · `PAPER_CONTAINER_CHANGED=NO` ·
`CERTIFICATION_TOUCHED=NO` · Silver/Gold sin `.part` · `progress.yaml` intacto ·
`src/domain/risk/` intacto · PaperEngine intacto.

## 10. Pendiente (fuera de este alcance)

Corrida de 647 días (62112 velas) OLD-vs-NEW por estrategia sobre el Gold Full DEVELOPMENT
(`gold-replay-5ca68f44…`) con `--expect-common-window`, y su análisis económico posterior al
gate. Requiere autorización explícita.

# M7 — Trade-Level Replay Engine (dos relojes)

**Fecha:** 2026-09-28 (UTC-6)
**Rama:** `medalion` @ `04441adc114041a4984f37e630c2c3b3dde0c408` (precondición verificada)
**Alcance:** motor de replay trade-a-trade determinista que consume el dataset Gold
`gold-replay-a8c49e0b…` (2024-06-01/02/03) y escribe un ledger JSONL reproducible en
`/srv/fast/medallion/replay-work/ledger.jsonl`, con decisiones guionizadas para validar
los contratos (trigger/fill, riesgo, contabilidad) — **no** es la estrategia real.
**Destino de salida:** `/srv/fast/medallion/replay-work/` (fuera de git; Silver/Bronze/Gold
intocados).
**Gate:** instrucción directa del usuario (M7). Restricciones: NO commit, NO push, NO bulk,
NO WF, NO holdout, NO M8, NO tocar paper-runner, DETENERSE tras SALIDA.

## Qué se implementó

| Archivo | Rol |
|---|---|
| `src/infrastructure/medallion/replay.py` | Motor dos relojes + validación FAIL CLOSED del dataset + ledger determinista: `validate_dataset`, `load_candles`, `iter_trades`, `replay_engine`, `ledger_payload`, `write_ledger`; Protocol `DecisionProvider`; `ScriptedScheduleProvider`; errores `ReplayError`/`DatasetValidationError`/`LedgerConflictError` (reexporta `InputHashMismatchError`) |
| `src/infrastructure/medallion/replay_cli.py` | CLI stdlib: `--dataset-dir --trades-dir --candles-dir --ledger-path [--require-marker]`; `STATUS=` + `SUMMARY=`; exit 0/1/2 |
| `tests/test_trade_replay.py` | 77 unit tests sin red (TDD: RED observado → GREEN) |

### Modelo de dos relojes (ADR-0005)

- **Reloj de decisión (velas 15m confirmadas):** `_advance(cutoff)` encola decisiones cuando
  `close_time <= cutoff` — nunca se ve una vela no confirmada (no lookahead). Contexto 1h/4h
  para `ContextSnapshot` (el proveedor guionizado lo ignora).
- **Reloj de ejecución (trades Silver):** por cada trade, en orden estricto:
  ① fill de exit pendiente → ② drenaje FIFO de decisiones (abre/cierra) → ③ evaluación de
  riesgo (actualiza path, trailing **antes** de elevar, decide trigger). El trade de fill
  **no** actualiza el path de riesgo (`ts <= entry_fill_ts` se salta) ⇒ MFE/MAE incluyen el
  trade gatillo pero no el de fill.
- **Fill:** primer trade con `ts >= trigger` (`first eligible trade`, confirmado por
  re-walk: `prev.ts < trigger <= fill.ts`). Riesgo: fill = **siguiente trade** al gatillo
  (`fill_index - trigger_index ∈ {0,1}`; `1` en el caso normal, `0` = edge fill al final
  del dataset con `fill_ts == trigger_ts`).
- **Sweep final:** decisiones encoladas sin fill → `decisions_unfilled`; exit pendiente →
  edge fill; posición abierta → `end_of_dataset` sobre el último trade.

### Semántica de salida (catálogo exacto §11)

`stop_loss` (protective ≤ entrada, ref = protective) · `trailing_stop` (protective > entrada,
exige `trailing_updates ≥ 1`) · `take_profit` (ref = target exacto) · `strategy_exit`
(SELL guionizado con posición abierta; trigger = close de vela, `trigger_trade_index = null`)
· `max_time_in_position` (catálogo, **no** implementado en M7) · `end_of_dataset` (sweep).

Clasificación exacta por referencia en el gatillo: `trailing_stop ⟺ ref > entry_execution`,
`stop_loss ⟺ ref ≤ entry_execution`, `take_profit ⟺ ref == initial_target`.

### Contabilidad (escenario `scripted-default-v1`)

`entry_execution = entry_trade × (1 + 5bps)` · `exit_execution = exit_trade × (1 − 5bps)` ·
`initial_stop = entry_execution − 2×ATR(14 Wilder)` · `target = entry_execution + 1.5×R` ·
`gross = (exit_trade − entry_trade) × qty(0.01)` ·
`slippage = 5bps × (entry_trade + exit_trade) × qty` ·
`fees = 0.001 × (entry_execution + exit_execution) × qty` ·
`net = gross − slippage − fees`. MFE/MAE identidades exactas contra `highest_price`.

### Validación FAIL CLOSED (antes de leer Silver)

`manifest → dates → split guard DEVELOPMENT (antes de tocar nada) → config sha → estructura
→ source_roots (layout relativo) → file lists/traversal → linaje → identidad (recompute ==
manifest == dirname) → hashes de 3+21 entradas`. Ledger: escritura `.part` + round-trip +
`os.replace`; idéntico ⇒ `skipped`; distinto ⇒ `LedgerConflictError`; sin wall-clock.

## Ejecución (evidencia en `docs/phases/23/evidence/`)

| Paso | Artefacto | Resultado |
|---|---|---|
| 01 unit + coverage | `m7-01-unit-tests.log` | **PASS** — ruff/format/mypy + **240 tests** medallion; capa **94.01%** (replay.py **91%**, replay_cli 96%) |
| 02 repo quality | `m7-02-repo-quality.log` | **PASS** — suite completa **1184 passed, 1 skipped** |
| 03 preflight | `m7-03-preflight.log` | **PASS** — Gold intacto (2 archivos, hashes `9411a4e0…`/`be8aae2d…`), Silver 3+21 re-hasheados (1 880 793), paper `Up 9 days` baseline, `REPLAY_WORK=LIMPIO`, Python 3.12.3 |
| 04 deploy copy | `m7-04-deploy-copy.log` + `m7-04b-deploy-copy.log` (intentos fallidos: falta `domain/`, import `LineageMismatchError`) + `m7-04c-deploy-copy.log` | **PASS** — → `/tmp/m7/src` (infrastructure+domain); `IMPORT_OK`, 27 campos, escenario/riesgo verificados, CLI `--help` OK |
| 05 UAT RUN1 | `m7-05-uat-run1.log` | **PASS** — `STATUS=created`, `decisions_total=45 filled=23 dropped=22 unfilled=0 closed=23 trades=1880793` (10 s); ledger 24 líneas; motivos `{stop_loss:16, take_profit:2, trailing_stop:5}`; 0 `.part` |
| 06 RUN2 + determinismo | `m7-06-uat-run2-determinism.log` (intento con `diff` de rutas, exit 1) + `m7-06b-uat-run2-determinism.log` | **PASS** — salida 2ª idéntica byte-a-byte (`RUN2_LEDGER_IDENTICAL=YES`, sha `6d64b62b…`), re-ejecución sobre canónico ⇒ `STATUS=skipped` sin cambios |
| 07 verificación independiente | `m7-07-uat-verify.log` | **PASS** — re-walk sin motor: 23 registros, stream 1 880 793 monotónico, fills primer-elegible, trigger == close de vela (288 velas), contabilidad/riesgo/MFE exactos, 27 campos; negativos N1–N6 FAIL CLOSED (split antes de leer, config sha, identidad, `InputHashMismatchError`, `LedgerConflictError`, exit 2); Gold+Silver+ledger intactos; `PAPER_CONTAINER_CHANGED=NO`; `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0` |

## Resultados UAT (lenovosrv)

- **DATASET_ID** = `gold-replay-a8c49e0be9154194841a97c4f26225a76cef9fba8d9a6d080198359c124ebdc3`
- **Ledger** = `/srv/fast/medallion/replay-work/ledger.jsonl` · sha256
  `6d64b62b48575bdbcda19eb0dbbc46d53a7351606eb5fd93a9c038643a83e625` (RUN1 = RUN2 byte-a-byte)
- Stats reales: `total=45, filled=23, dropped=22, unfilled=0, closed=23`,
  `trades=1880793`, motivos `stop_loss:16, take_profit:2, trailing_stop:5`
  (0 `strategy_exit` en este dataset: los 22 SELLs cayeron con posición ya cerrada por riesgo)
- RUN1 `created=1` (10 s) → RUN2 idéntico → re-run `skipped=1` (0 cambios)
- Silver re-hasheado tras toda la operación (intacto); paper-runner sin cambios

## Tests (77 casos, `tests/test_trade_replay.py`)

Validación: manifest/dates/config/estructura/source_roots/linaje/identidad/hashes ⇒ FAIL ·
split guard WF **y** holdout antes de leer · dirname/identidad · iter_trades (header, columnas,
orden, símbolo, conteo) · load_candles (orden, duración, day-bounds, timeframe faltante) ·
ScriptedScheduleProvider (compra/venta/ATR/índices) · motor: fill primer elegible, drenaje
FIFO, drop con posición abierta, stop/take/trailing con path, edge fill, sweep unfilled,
`end_of_dataset`, orden fill→drain→risk · contabilidad exacta (gross/slip/fees/net) ·
MFE/MAE identidades · ledgers: run_meta 21 claves, 27 campos, catálogo, sin wall-clock,
created/skipped/`LedgerConflictError`, `.part`+round-trip · CLI exit 0/1/2 · errores.

## Condiciones de la regla M7 (post-ejecución)

1. Solo dataset DEVELOPMENT 2024-06-01/02/03; NO bulk; NO WF; NO holdout — PASS (`m7-03/05/07`)
2. Split guard antes de leer (dirs inexistentes ⇒ `fuera de DEVELOPMENT`) — PASS (`m7-07` N1)
3. Determinismo: RUN2 byte-idéntico + idempotencia `skipped` — PASS (`m7-06b`)
4. Re-walk independiente valida fills/riesgo/contabilidad sin el motor — PASS (`m7-07`)
5. FAIL CLOSED: config/identidad/hash Silver/ledger conflict/usage — PASS (`m7-07` N2–N6)
6. Silver/Bronze/Gold intactos; ledger canónico sin `.part` — PASS (`m7-03/05/07`)
7. Paper-runner intocado (`PAPER_CONTAINER_CHANGED=NO`) — PASS (`m7-07`)
8. Cobertura capa medallion ≥90% (94.01%) + suite completa — PASS (`m7-01/02`)
9. Evidencia `m7-*` + doc creadas — PASS

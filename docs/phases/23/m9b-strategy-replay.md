# M9-B — Strategy Provider + Risk Engine Integration (smoke 3 días)

**Fecha:** 2026-09-29 (UTC-6)
**Rama:** `medalion` @ `5dbc1c3c871a743cd0a54274fcc4fdce18e54d1f` (precondición verificada;
cambios en worktree, **sin commit** por restricción de gate)
**Alcance:** integración mínima y opt-in de las tres estrategias congeladas del Lab
(`EmaRsiBaseline`, `EthDonchianBreakout`, `EthBollingerMeanReversion`) con el Trade-Level
Replay M7: adaptador `StrategyDecisionProvider` + sizing dinámico vía `RiskEngine`
(escenario Phase 22B explícito `m9b-22b-parity-v1`), preservando **byte-idéntico** el
ledger M7 scripted de 3 días.
**Smoke:** solo dataset Gold de 3 días
`gold-replay-a8c49e0be9154194841a97c4f26225a76cef9fba8d9a6d080198359c124ebdc3`
(2024-06-01/02/03, `PARTIAL`), 2 corridas por estrategia.
**Gate:** instrucción directa del usuario (M9-B1). Restricciones: NO FULL DEVELOPMENT,
NO MARK-DONE, NO COMMIT, NO PUSH, NO tocar `progress.yaml`, NO paper-runner/certification/
safeguard/Gold UAT, DETENERSE tras SALIDA.

## Qué se implementó

| Archivo | Rol |
|---|---|
| `src/infrastructure/medallion/strategy_provider.py` (**nuevo**) | `StrategyDecisionProvider` (adaptador estrategia → `DecisionProvider`): conversión `CandleRow→Candle` (`timestamp_ms=open_time`), orden estricto de `candle_index` FAIL CLOSED, `decision_ts==close_time` obligatorio, aserción `Signal.timestamp_ms==open_time`, `HOLD→None`/`BUY→Decision("buy")`/`SELL→Decision("sell")`, `signal_ts=decision_ts`, `reference_price=candle.close`, `atr=atr_value`; `rows_to_domain_candles` |
| `src/infrastructure/medallion/replay.py` | `ReplayScenario` + `sizing_mode` (`fixed`/`risk_engine`) e `intensity` con validación `__post_init__` FAIL CLOSED; `ReplayResult.rejected_reasons`; en `_Engine` solo si dinámico: `RiskEngine`, `KillSwitchState`, capital/pnl realizado/pnl diario/peak equity; `_evaluate_risk` (evalúa en el **primer trade elegible**, inmediatamente antes de abrir) y `_open_position(verdict)` (stop/target/quantity **del veredicto**, base `reference_price`); contadores `decisions_rejected` + motivos; `_finish` actualiza pnl realizado cuando dinámico; meta del ledger con claves nuevas **solo** `sizing_mode != "fixed"` |
| `src/infrastructure/medallion/replay_cli.py` | `--strategy {scripted,ema-rsi,donchian,bollinger}` (default `scripted`) y `--sizing-mode {fixed,risk_engine}` (default: `fixed` para scripted ⇒ **ruta legacy exacta** `DEFAULT_SCENARIO`; `risk_engine` para estrategias); `_m9b_scenario` (22B explícito: `RiskConfig(stop_loss_required=True, version="risk-v2-atr-exit")`, fee 10 bps, slippage 2 bps, ATR 14, medium); `_build_strategy` composition-root con import diferido; línea `SIZING=` en stdout **solo** cuando dinámico |
| `tests/test_strategy_provider.py` (**nuevo**) | mapeo HOLD/BUY/SELL, `signal_ts==close_time` y nunca `open_time`, FAIL CLOSED (ts/orden/acción/índice fuera de rango), contexto ignorado, paridad de señales ×3 estrategias, `rows_to_domain_candles` |
| `tests/test_strategy_replay_no_lookahead.py` (**nuevo**) | corruptor de prefijo ×3 estrategias (ninguna decisión usa información futura), contexto futuro no cambia decisiones, determinismo bit a bit |
| `tests/test_trade_replay.py` | sección M9-B: sizing dinámico/referencia/costes, estado entre round-trips, rechazo de RiskEngine, bypass legacy (spy `RiskEngine` **no** instanciado en `fixed`), meta fija sin claves de sizing, validación `sizing_mode`/`intensity`, 5 tests CLI |

**Sin cambios** en `src/domain/risk/*` (reutilización pura), en las tres estrategias, ni en
el paper-runner/certification/safeguard.

## Diseño (decisiones cerradas por el usuario en M9-B1)

1. **Momento de evaluación:** el RiskEngine se evalúa en el **primer trade elegible,
   inmediatamente antes de abrir** (orden del motor: advance → fill pending exit → drain
   decisión → `RiskEngine.evaluate` → open si APPROVED → risk eval). Nunca se pre-apueba
   en el cierre de la vela.
2. **Propuesta:** `TradeProposal(action=BUY, intensity, price=Decision.reference_price,
   atr=Decision.atr, timestamp_ms=Decision.signal_ts)`; el precio del trade histórico nunca
   sustituye `reference_price`.
3. **Stops/target del veredicto** con base `reference_price`:
   `stop = ref − 2.0×ATR`, `target = ref + 2.0×(ref − stop)`; el fill usa el trade ±
   slippage (`entry_execution = trade×(1+2bps)`).
4. **Escenario 22B explícito** (`m9b-22b-parity-v1`): stop 2.0 / tp_r 2.0 / trailing 3.0 /
   fee 10 bps / slippage 2 bps / intensity `medium` / `risk_version="risk-v2-atr-exit"`.
   Nunca se heredan en silencio los defaults M7 (1.5/1.0/5 bps/0.01).
5. **Backward compat:** scripted legacy intacto (`DEFAULT_SCENARIO`, ruta exacta M7);
   dinámico solo opt-in. Meta del ledger con claves de auditoría (`sizing_mode`,
   `intensity`, `decisions_rejected`, `rejected_reasons`) **solo** en modo dinámico ⇒
   ledger legacy byte-idéntico.
6. **Adapter FAIL CLOSED** en orden/ timestamps; estrategias no modificadas y no se
   duplican fórmulas de sizing (todo pasa por `RiskEngine.compute_position_size`).
7. **Contabilidad dinámica:** `decisions_total = filled + dropped + unfilled + rejected`;
   rechazos auditados por motivo en `stats`/meta.

## Ejecución (evidencia en `docs/phases/23/evidence/`)

| Paso | Artefacto | Resultado |
|---|---|---|
| 01 calidad repo | `m9b-01-repo-quality.log` | **PASS** — `ruff check` + `ruff format --check` + `mypy src tests` (290 archivos, 0 errores) |
| 02 suite completa | `m9b-02-unit-tests-full.log` | **PASS** — `pytest --ignore=tests/integration --cov=src --cov-branch --cov-fail-under=90` → **90.55%** |
| 03 scope medallion | `m9b-03-medallion-scoped.log` (87%, set incompleto → exit 1) + `m9b-03b-medallion-scoped.log` | **PASS** — set completo (bronze/silver/gold/split/replay/cli/strategy): **94.25%** (replay.py 91%, strategy_provider 91%, replay_cli 91%) |
| 04 conteo tests | `m9b-04-unit-tests-count.log` | **PASS** — **1258 passed, 1 skipped** (base M9a1: 1227 ⇒ **+31 tests nuevos**) |
| 05 preflight | `m9b-05-preflight.log` / `05b` (conteos pre-M9a) / `m9b-05c-preflight.log` | **PASS** — marker/dataset OK, fechas `[2024-06-01..03]` DEVELOPMENT, Silver 647+4529 sin `.part`, ledger legacy `6d64b62b…` intacto, 2 datasets replay (smoke usa solo el de 3 días), paper baseline, sin vars WF/holdout |
| 06 deploy | `m9b-06-deploy.log` (typo rama `medallon`) + `m9b-06b-deploy.log` | **PASS** — → `/tmp/m9b/src` (infrastructure+domain+lab); `IMPORT_OK`, escenario 22B y legacy verificados, rechazo `sizing_mode`/`intensity` inválidos, versiones de estrategias, CLI `--help` con flags nuevos |
| 07 UAT RUN1 | `m9b-07-uat-run1.log` | **PASS** — 3 estrategias ×1 (`STATUS=created`, `trades=1880793`, línea `SIZING=dynamic mode=risk_engine intensity=medium`), ~9–10 s c/u, 0 `.part` |
| 08 RUN2 + determinismo + legacy | `m9b-08-uat-run2-determinism.log` | **PASS** — RUN1==RUN2 byte-a-byte (ledger **y** stdout) por estrategia; regeneración legacy sin flags ⇒ sha `6d64b62b48575bdbcda19eb0dbbc46d53a7351606eb5fd93a9c038643a83e625` **== M7 canónico** (`LEGACY_M7_LEDGER_IDENTICAL=PASS`); canónico original sin tocar |
| 09 verificación | `m9b-09-uat-verify.log` (glob fechas) + `09b` (baseline paper) + `m9b-09c-uat-verify.log` | **PASS** — contrato de ledger dinámico ×3 (meta con 25 claves; `reference_price == close` de la vela de decisión; stop/target exactos desde `ref`/`ATR`; notional ≤ 2% capital; fees/slippage > 0; `fill ≥ trigger`; exit_reason ∈ catálogo; MFE/MAE finitos; sin wall-clock; contabilidad `total=filled+dropped+unfilled+rejected`), legacy meta **21 claves exactas**, Silver re-hasheado intacto, `PAPER_CONTAINER_CHANGED=NO`, `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0` |
| 10 safety repo | `m9b-10-repo-safety.log` | **PASS** — HEAD `5dbc1c3`/`medalion`; solo archivos intencionales modificados; `PAPER_CERT_SAFEGUARD_UNTOUCHED=YES`, `CERTIFICATION_TOUCHED=NO` |

## Resultados del smoke (lenovosrv — SOLO mecanismo, sin conclusiones de rentabilidad)

Ledgers en `/srv/fast/medallion/m9b-work/` (fuera de git; `replay-work/` canónico intacto):

| Estrategia | total | filled | dropped | unfilled | rejected | closed | exits | ledger sha256 (RUN1==RUN2) |
|---|---|---|---|---|---|---|---|---|
| `ema-rsi` (`baseline-v1`) | 3 | 1 | 2 | 0 | 0 (`{}`) | 1 | `stop_loss:1` | `52823a0dbcffa80430d7b26d537f8f8cce1537f575b19413220ebdf23b85d908` |
| `donchian` (`eth-donchian-breakout-v1`) | 22 | 3 | 19 | 0 | 0 (`{}`) | 3 | `stop_loss:3` | `36bbccd47d0a997fff63cafb20e024921cd79c9cbe7292183c95ee5a9d25492b` |
| `bollinger` (`eth-bollinger-mean-reversion-v1`) | 149 | 6 | 142 | 1 | 0 (`{}`) | 4 | `stop_loss:2, strategy_exit:2` | `05fc6f12d11b124842405865db4068ba10e4b682225aa5b27834cba842aae795` |

- `EXIT_TRIGGER_FILL_DIFF=2` (fill ≥ trigger en todos los registros).
- Legacy M7 regenerado: `total=45 filled=23 dropped=22 unfilled=0 closed=23`,
  motivos `stop_loss:16, take_profit:2, trailing_stop:5`, sin línea `SIZING=` ⇒
  meta de 21 claves exacta, sha idéntico al UAT M7.
- `decisions_rejected=0` en las 3 corridas: sin rechazos en 3 días (drawdown/daily-loss no
  se activan en esta ventana); la ruta de rechazo está cubierta por unit tests
  (`max_drawdown=0.0` ⇒ `{"max_drawdown": 1}`).

## Tests (+31 sobre base M9a1; 1258 passed, 1 skipped)

- **`test_strategy_provider` (16)** — mapeo, timestamps, FAIL CLOSED ×5, contexto, paridad ×3,
  `rows_to_domain_candles`.
- **`test_strategy_replay_no_lookahead` (3)** — corruptor de prefijo ×3, contexto ignorado,
  determinismo.
- **`test_trade_replay` sección M9-B (+12)** — `spy_risk_engine` (nunca instanciado en
  `fixed`), stop/target/dinámico exactos, costes (fees 10 bps + slippage 2 bps), estado
  entre round-trips, rechazo auditado, meta fija sin claves de sizing, validación de
  `sizing_mode`/`intensity`, CLI (`--strategy`, `--sizing-mode`, defaults, legacy, exit 2).
- TDD: RED observado (`ModuleNotFoundError`, argparse `unrecognized arguments`,
  `FAIL CLOSED` de fixtures) → GREEN verificado.
- Cobertura: global **90.55%** (≥90) · scope medallion **94.25%** (≥90).

## Condiciones de la regla M9-B1 (post-ejecución)

1. Solo smoke sobre Gold 3 días (2024-06-01/02/03); NO full development — PASS (`m9b-05c/07/08`)
2. RUN1==RUN2 byte-a-byte por estrategia — PASS (`m9b-08`)
3. Ledger M7 legacy byte-idéntico (`6d64b62b…`) y canónico sin tocar — PASS (`m9b-08/09c`)
4. Paridad de señales adapter vs `on_candle` directo ×3 — PASS (unit `m9b-01/02`)
5. Sin lookahead (reference_price = close confirmado; stop/target desde ref) — PASS (unit + `m9b-09c`)
6. Riesgo 22B explícito, nunca defaults M7; RiskEngine reutilizado sin duplicar — PASS (`m9b-06b/09c`)
7. Contabilidad/auditoría: `decisions_rejected` + motivos en meta dinámica; meta legacy intacta — PASS (`m9b-09c`)
8. Safety: `PAPER_CONTAINER_CHANGED=NO`, `CERTIFICATION_TOUCHED=NO`,
   `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0`, Silver/Gold intactos — PASS (`m9b-09c/10`)
9. Evidencia `m9b-*` + este doc creados; **sin** tocar `progress.yaml` — PASS
10. `POPULATIONS_DIRECTLY_COMPARABLE=NO`: los 3 ledgers dinámicos NO son comparables entre
    sí ni con el legacy scripted en rentabilidad (diferente estrategia, sizing, escenario de
    riesgo y costes); este smoke valida **mecanismo**, no desempeño.

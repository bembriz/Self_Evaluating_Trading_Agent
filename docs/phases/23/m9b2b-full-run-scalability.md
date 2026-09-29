# M9-B2B — Full-run scalability + artefactos económicos (runner de ventana común)

**Fecha:** 2026-09-29 (UTC-6)
**Rama:** `medalion` @ `c3bb67d702ff39627630406c54741b2afb66b46d` (cambios en worktree, **sin commit**)
**Alcance:** dejar `harness/scripts/m9b_common_window.py` listo para ejecutar los 647 días
sin materializar todos los trades en RAM y produciendo, en una sola pasada, todos los
artefactos económicos (summary + ledger por combinación strategy/model).
**NO ejecuta** la corrida de 647 días. **NO** mark-done. **NO** commit/push. Gate posterior.

---

## 1. Streaming obligatorio (NEW)

- `run_new_trade_sequence(trades: Iterable[ReplayTrade])` recibe un **iterable** y lo pasa
  directo a `replay_engine(...)`. Eliminado `trades = list(_window_trades(...))` y el
  `list(trades)` interno.
- El motor M7 (`_Engine.run`) itera `self._trades` **una sola vez**; no se materializa la
  lista de trades Silver.
- Se conserva: orden cronológico, FAIL CLOSED de `iter_trades` (orden y `row_count`),
  misma semántica económica y misma paridad de señales.
- Test: `test_new_accepts_single_pass_iterator_without_materializing` (spy sobre
  `replay_engine` confirma que recibe un **iterator**, no una `list`) y
  `test_new_accepts_generator_expression`.

## 2. Artefactos por corrida (`--output-dir`)

Por combinación `strategy` × `model`:

```text
<strategy>-<model>-summary.json
<strategy>-<model>-trades.jsonl
```

- Escritura atómica `.part → round-trip verify → rename(2)` (`write_artifact`).
- Mismo contenido ⇒ `skipped` (idempotente). Contenido distinto ⇒
  `ArtifactConflictError` (**FAIL CLOSED**).
- JSON/JSONL canónicos: `sort_keys=True`, `separators=(",",":")`, `ensure_ascii=True`.

## 3. Ledger económico

Campos mínimos obligatorios (`LEDGER_REQUIRED_FIELDS`) en OLD y NEW: `entry_timestamp`,
`exit_timestamp`, `entry_reference_price`, `entry_execution_price`,
`exit_reference_price`, `exit_execution_price`, `quantity`, `exit_reason` (raw),
`exit_reason_presentation`, `gross_reference_pnl`, `gross_execution_pnl`, `fees`,
`slippage`, `net_pnl`, `holding_ms`.

NEW preserva además (`LEDGER_EXTENDED_FIELDS`): `entry_trigger_timestamp`,
`exit_trigger_timestamp`, `mfe`, `mae`, `stop`, `target`, `strategy_version`,
`risk_version`, `execution_model`, `execution_model_version`.

Identidad contable mantenida en ambos modelos: `net_pnl = gross_execution_pnl − fees`
(la slippage ya está embebida en el precio de ejecución; se reporta aparte).
**PaperEngine no se altera** (OLD lee sus `Fill`/eventos y arma el ledger en el runner).

## 4. Summary comparable OLD/NEW

Misma definición para ambos modelos (`summarize_ledger`):

`closed_trades`, `gross_reference_pnl`, `gross_execution_pnl`, `fees`, `slippage`,
`net_pnl`, `expectancy`, `profit_factor` (= Σ win / |Σ loss|, `None` si no hay pérdidas),
`win_rate` (net > 0), `average_holding_ms`, `exit_reason_counts_raw`,
`exit_reason_counts_presentation`, `final_equity`.

- `final_equity = capital + net realizado` (**REALIZED-ONLY**); no se mezcla el equity
  mark-to-market de OLD con realized-only de NEW.
- `max_drawdown_abs` / `max_drawdown_pct` sobre la **curva de equity realizada ordenada por
  cierre de trade**; `MAX_DRAWDOWN_BASIS=REALIZED_CLOSED_TRADES`.
- `PROFIT_FACTOR_BASIS=NET_REALIZED`.

## 5. Identidades del summary

`code_git_sha`, `dataset_id`, `dataset_sha`, `common_window_start`,
`common_window_end_exclusive`, `candle_hash`, `signal_hash`, `strategy_version`,
`risk_version`, `execution_model`, `fee_bps`, `slippage_bps`, `stop_atr`, `target_r`,
`trailing_atr`, `summary_sha256` (auto-excluyente) y `trade_ledger_sha256`
(sha256 del archivo `trades.jsonl`).

## 6. Regresiones

| Verificación | Resultado |
|---|---|
| `COMMON_WINDOW_DAYS=647` / `COMMON_WINDOW_15M_CANDLES=62112` | PASS (test + guard) |
| `SAME_CANDLE_SOURCE_OLD_NEW=YES` | PASS (`candle_hash=3443d340…`) |
| `SIGNAL_HASH_PARITY=PASS` | PASS (3 estrategias) |
| Legacy M7 `6d64b62b48…` | **idéntico** (canónico + regenerado) |

## 7. Smoke (solo Gold 3 días · 2024-06-01..03 · 288 velas · sin conclusiones económicas)

Creados `summary.json` + `trades.jsonl` para OLD y NEW × `baseline/donchian/bollinger`:

| Estrategia | Modelo | closed | net_pnl (mecanismo) | summary file sha256 (prefijo) |
|---|---|---|---|---|
| baseline | OLD | 1 | −0.057226 | `7dcac913…` |
| baseline | NEW | 1 | −0.026717 | `f51ba45d…` |
| donchian | OLD | 2 | +0.024255 | `f1a7fca6…` |
| donchian | NEW | 3 | −0.325321 | `c3573160…` |
| bollinger | OLD | 4 | −0.176312 | `48bbbe68…` |
| bollinger | NEW | 4 | −0.264924 | `f341ccf0…` |

- **Determinismo**: `run1` vs `runfresh` byte-a-byte idénticos (summary y ledger) en las 6
  combinaciones.
- **Rerun** en el mismo `--output-dir`: `summary_status=skipped` y `trades_status=skipped`.
- **Conflicto** (trades.jsonl alterado): `ArtifactConflictError` rc=1 (**FAIL CLOSED**).
- Sin `.part` residual (`PART_FILES=0`), `ARTIFACT_FILES=12`.
- Los `net_pnl` son del mecanismo sobre 3 días: **NO** son conclusión económica.

## 8. Safety

`WALK_FORWARD_READS=0` · `FINAL_HOLDOUT_READS=0` · `PAPER_CONTAINER_CHANGED=NO` ·
`CERTIFICATION_TOUCHED=NO` · `progress.yaml` intacto · `src/domain/risk/` intacto ·
`PaperEngine` intacto · Silver/Gold sin `.part` · sin datasets holdout/walk-forward.

## 9. Evidencia (`docs/phases/23/evidence/`)

| Paso | Artefacto | Resultado |
|---|---|---|
| 01 calidad | `m9b2b-01-quality.log` | **PASS** — ruff + format + mypy (290 archivos) |
| 02 suite global | `m9b2b-02-tests-global.log` | **PASS** — 1263 passed, 1 skipped · **90.56%** |
| 03 scope medallion | `m9b2b-03-tests-medallion.log` | **PASS** — 323 passed · **94.27%** |
| 04 harness tests | `m9b2b-04-tests-harness.log` | **PASS** — 92 passed (2 fallos PDF pre-existentes excluidos); runner **75%** |
| 05 deploy | `m9b2b-05-deploy.log` | **PASS** — hashes local==host; import + contrato |
| 06 smoke | `m9b2b-06-smoke.log` | **PASS** — OLD×3/NEW×3, determinismo, SKIP, conflicto FAIL CLOSED, streaming |
| 07 verify | `m9b2b-07-verify.log` | **PASS** — integridad summary/ledger, legacy idéntico, paridad, safety |
| 08 secret scan | `m9b2b-08-secret-scan.log` | **PASS** — 6 patrones HITS=0; 0 hex-64 en código/tests |

## 10. Pendiente (fuera de alcance)

Corrida de 647 días (62112 velas) OLD-vs-NEW por estrategia sobre el Gold Full DEVELOPMENT
(`gold-replay-5ca68f44…`) con `--expect-common-window` y `--output-dir`, y su análisis
económico posterior al gate. Requiere autorización explícita.

---

## SALIDA

```text
MEDALLION_M9B2B=PASS

NEW_TRADES_STREAMED=YES
FULL_TRADE_LIST_MATERIALIZED=NO

SUMMARY_ARTIFACT=PASS
TRADE_LEDGER_ARTIFACT=PASS
ATOMIC_OUTPUT=PASS
IDEMPOTENT_RERUN=PASS

ECONOMIC_METRICS_COMPLETE=YES
MAX_DRAWDOWN_BASIS=REALIZED_CLOSED_TRADES

SIGNAL_HASH_PARITY=PASS
LEGACY_M7_LEDGER_IDENTICAL=YES

SMOKE_OLD_NEW=PASS
QUALITY=PASS

WALK_FORWARD_READS=0
FINAL_HOLDOUT_READS=0
PAPER_CONTAINER_CHANGED=NO
CERTIFICATION_TOUCHED=NO

READY_FOR_M9B2_COMMON_WINDOW_RUN=YES
```

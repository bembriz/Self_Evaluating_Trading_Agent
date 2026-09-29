# Commit Candidate Report — 2026-09-29

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> **Candidate 015 — M9-B2B: full-run scalability + artefactos económicos del runner de ventana común.**

## Objetivo

Dejar `harness/scripts/m9b_common_window.py` listo para ejecutar los **647 días** sin
materializar todos los trades Silver en RAM y produciendo, en una sola pasada, los
artefactos económicos del OLD-vs-NEW por combinación strategy/model:

- **streaming NEW**: `run_new_trade_sequence(trades: Iterable)` pasa el iterable directo a
  `replay_engine` (elimina `list(_window_trades(...))` / `list(trades)`);
- **ledger económico** por trade cerrado (entry/exit reference+execution, fees, slippage,
  net, holding; NEW preserva trigger tss, MFE/MAE, stop/target, versiones);
- **summary comparable OLD/NEW** con identidades (`summary_sha256`, `trade_ledger_sha256`)
  y max drawdown sobre la curva de equity **REALIZADA** (`MAX_DRAWDOWN_BASIS=REALIZED_CLOSED_TRADES`);
- **outputs atómicos/idempotentes** (`--output-dir`, `.part → verify → rename`; mismo
  contenido ⇒ SKIP; distinto ⇒ FAIL CLOSED);
- tests/docs/evidencia.

**NO** ejecuta la corrida de 647 días (gate posterior). **NO** toca PaperEngine,
`src/domain/risk/`, `progress.yaml` ni certificación.

## Rama

| Campo | Valor |
|---|---|
| branch | `medalion` |
| base commit | `c3bb67d702ff39627630406c54741b2afb66b46d` (HEAD == BASE esperado) |

## Archivos

- **Creados (13):**
  - `docs/phases/23/m9b2b-full-run-scalability.md` (doc de fase)
  - `docs/phases/23/commit-candidate-015.md` (este reporte)
  - **11 logs** `docs/phases/23/evidence/m9b2b-*.log` (8 de M9-B2B + 3 de este candidate)
- **Modificados (3):**
  - `harness/scripts/m9b_common_window.py` (+535/−43)
  - `harness/tests/test_m9b_common_window.py` (+394/−78)
  - `docs/phases/23/evidence/log.md` (+8, índice)
- **Eliminados:** ninguno
- **Total staged (previsto):** 16
- **Fuera de alcance:** 0 — sin `progress.yaml`, sin `src/domain/risk/`, sin `src/**`,
  sin paper runtime, sin deployment, sin certification/safeguard
  (`m9b2b-07-verify` §4-6, `m9b2b-cc015-secret-scan`)

## Diff

```bash
$ git diff --cached --stat        # snapshot (12 archivos, antes de este reporte)
 harness/scripts/m9b_common_window.py    | 578 +++++++++++++++++++++++++++++---
 harness/tests/test_m9b_common_window.py | 472 +++++++++++++++++++++-----
 docs/phases/23/evidence/log.md          |   8 +
 12 files changed, 1539 insertions(+), 121 deletions(-)

$ git diff --cached --numstat | grep -E '(src|harness|tests)/'
535  43  harness/scripts/m9b_common_window.py
394  78  harness/tests/test_m9b_common_window.py
```

Nota: el diff completo del runner incluye la refactorización del ledger/summary; el
`src/**` (motor M7) **no cambia** (`src/infrastructure/medallion/replay.py` sigue en
`bd3a16bb…`).

## Arquitectura afectada

- **Herramienta del arnés** `harness/scripts/m9b_common_window.py` (no es código de
  producto): API pública añadida `ModelRun`, `summarize_ledger`, `build_summary`,
  `summary_identities`, `write_run_artifacts`, `write_artifact`, `artifact_paths`,
  `ledger_jsonl_bytes`; firmas de `run_old_close_only`/`run_new_trade_sequence` ahora
  devuelven `ModelRun` (reporte + ledger).
- **Contratos consumidos sin cambio:** `infrastructure.medallion.replay` (`replay_engine`,
  `iter_trades`, `ReplayResult`), `PaperEngine`/`Portfolio` (solo lectura de `Fill`),
  `RiskEngine` (vía escenario 22B existente).
- **Sin cambios:** `src/**` (0 archivos), `src/domain/risk/*`, `PaperEngine`, estrategias
  del Lab, `replay_cli`.
- **Blast radius (codebase-memory `detect_changes since=c3bb67d`):** `changed_files=12`
  (12 pre-reporte), `seed_symbols=66`, `impacted_total=2` — confinado a
  `harness/scripts` (1) y `harness/tests` (1). **Impacto en `src/`: 0.** El runner y sus
  tests están fuera del grafo de producto (harness); se leyó su fuente directamente.

## Índice del grafo

- [ ] Índice re-indexado tras el commit (`index_repository`) → *pendiente de APPROVED (§4.13)*
- [x] Cobertura consultada pre-ejecución (`check_index_coverage`):
  `harness/scripts/m9b_common_window.py` y `harness/tests/test_m9b_common_window.py`
  → `no_recorded_issue` con `freshness=metadata_match`; scopes `harness/scripts` y
  `harness/tests` → solo `__pycache__` excluido por diseño. Sin `parse_partial`. Fuente
  leída directamente (el agente es el autor). Reindex post-commit pendiente.

## Validaciones (SALIDA M9-B2B)

| Requisito | Resultado | Evidencia |
|---|---|---|
| `NEW_TRADES_STREAMED=YES` | **YES** (spy: el motor recibe un iterator, no lista) | `m9b2b-04`, `m9b2b-06` §8 |
| `FULL_TRADE_LIST_MATERIALIZED=NO` | **NO** (`MATERIALIZED_LIST=ABSENT`, `TRADES_LIST_CAST=ABSENT`) | `m9b2b-06` §8 |
| `ECONOMIC_METRICS_COMPLETE=YES` | **YES** (14 métricas + exit counts + final_equity + DD) | `m9b2b-07` §1 |
| `MAX_DRAWDOWN_BASIS=REALIZED_CLOSED_TRADES` | **PASS** | `m9b2b-06`, `m9b2b-07` |
| `SIGNAL_HASH_PARITY=PASS` | **PASS** (3 estrategias) | `m9b2b-06` §5, `m9b2b-07` §3 |
| `LEGACY_M7_LEDGER_IDENTICAL=YES` | **YES** (`6d64b62b…` canónico + regen) | `m9b2b-07` §2 |
| `SUMMARY_ARTIFACT` / `TRADE_LEDGER_ARTIFACT` | **PASS** | `m9b2b-06` §1-4 |
| `ATOMIC_OUTPUT` / `IDEMPOTENT_RERUN` | **PASS** (SKIP; `.part=0`) | `m9b2b-06` §2,7 |
| Conflicto distinto FAIL CLOSED | **PASS** (`ArtifactConflictError` rc=1) | `m9b2b-06` §6 |
| quality PASS | **PASS** | `m9b2b-01-quality` |
| secret scan PASS | **PASS** (7 patrones HITS=0) | `m9b2b-08`, `m9b2b-cc015-secret-scan` |
| `progress.yaml` sin cambios | **YES** | `m9b2b-07` §4 |
| `src/domain/risk/` sin cambios | **YES** | `m9b2b-07` §4 |
| paper/certification intactos | **YES** (`PAPER_CONTAINER_CHANGED=NO`) | `m9b2b-07` §5 |
| WF/HOLDOUT reads=0 | **YES** (`0`; sin datasets holdout/walk-forward) | `m9b2b-07` §6 |

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Calidad (ruff + format + mypy, 290 archivos) | **PASS** | `m9b2b-01-quality` |
| Suite global (`--cov=src --cov-fail-under=90`, sin integration) | **PASS** — 1263 passed, 1 skipped · **90.56%** | `m9b2b-02-tests-global` |
| Scope medallion | **PASS** — 323 passed · **94.27%** | `m9b2b-03-tests-medallion` |
| Harness tests | **PASS** — 92 passed (2 fallos PDF **pre-existentes** excluidos) | `m9b2b-04-tests-harness` |
| Cobertura aislada del runner | **75%** (`m9b_common_window.py`: 376 stmts, 83 miss) — sube desde 69%; líneas no cubiertas = `main()`/CLI/IO validados en el smoke host | `m9b2b-04-tests-harness` |
| Smoke host 3 días (ÓLD×3/NEW×3) | **PASS** — determinismo byte-a-byte, rerun SKIP, conflicto FAIL CLOSED, paridad | `m9b2b-06-smoke` |
| Verify (integridad + legacy + safety) | **PASS** | `m9b2b-07-verify` |

## Cobertura

**Global 90.56%** (≥90) · **medallion 94.27%** (≥90) · **harness/scripts runner 75%**
(documentado; `harness/scripts` no es `src/`). Números exactos en los logs citados.

## Calidad

```bash
uv run ruff check .                 # All checks passed!
uv run ruff format --check .        # 333 files already formatted
uv run mypy src tests               # Success: no issues found in 290 source files
uv run pytest tests --ignore=tests/integration -o addopts= -q --cov=src --cov-branch --cov-fail-under=90
                                    # 1263 passed, 1 skipped · 90.56%
git diff --cached --check           # RC=0 (full y scoped)
```

## Seguridad

- [x] Sin secretos en el diff staged: **7 patrones HITS=0** (clave privada, `AKIA…`,
  asignaciones de credenciales, `Bearer …`, URL `user:pass@`, archivos sensibles, hex-64
  fuera de logs) — `m9b2b-cc015-secret-scan`
- [x] Sin `.env`/`.pem`/`.key`/`id_rsa`/`.p12` staged
- [x] Hex-64 fuera de logs: **1** — `6d64b62b48575bdbcda19eb0dbbc46d53a7351606eb5fd93a9c038643a83e625`
  (legacy M7 ledger SHA **documentado**, hash público de artefacto, no credencial) en este
  reporte; **código y tests: 0 hex-64**

## Smoke (solo Gold 3 días · sin conclusiones económicas)

`m9b2b-06`: 6 combinaciones ×2 dirs (run1/fresh) **byte-idénticas**; rerun
`summary_status=skipped` + `trades_status=skipped`; conflicto `ArtifactConflictError`
rc=1; `PART_FILES=0`; streaming sin materialización. Paridad:
`baseline 059f2d64…`, `donchian 91356974…`, `bollinger 3141b4a5…`.
`LEGACY_M7_LEDGER_IDENTICAL=YES` (`6d64b62b48575bdbcda19eb0dbbc46d53a7351606eb5fd93a9c038643a83e625`).

## Seguridad de infraestructura

`WALK_FORWARD_READS=0` · `FINAL_HOLDOUT_READS=0` · `PAPER_CONTAINER_CHANGED=NO` ·
`CERTIFICATION_TOUCHED=NO` · `PROGRESS_YAML_UNTOUCHED=YES` · Silver/Gold sin `.part` ·
`src/domain/risk/` intacto · `PaperEngine` intacto (`m9b2b-07`).

## Riesgos

- El summary incorpora `code_git_sha`; con worktree sucio el sha corresponde al HEAD base
  (`c3bb67d`), no al diff exacto. Tras el commit autorizado, una corrida nueva ya fijará
  el sha del commit.
- La cobertura del runner es 75% (camino `main()`/CLI): el contrato puro está cubierto por
  tests y el camino CLI por el smoke host (6 corridas + guard).
- El smoke es de 3 días y sin lectura económica: la corrida de 647 días es otro gate.
- `profit_factor` es `None` cuando no hay pérdidas (no hay `inf` en JSON); documentado.

## Deuda técnica

- Los scripts de smoke viven en `/tmp/opencode/` (fuera del repo); el runner sí está
  versionado.
- El contrato `ModelRun` cambia las firmas de las funciones de corrida (internas del
  runner); no afecta a `src/`.
- Elevar la cobertura del runner (main/IO) requeriría un fixture Gold en `harness/tests`.

## Mensaje de commit propuesto

```
feat(medallion): harden common-window full replay

- streaming obligatorio en NEW: run_new_trade_sequence recibe Iterable[ReplayTrade]
  y lo pasa directo a replay_engine (sin list()); test con spy confirma iterator
- ledger economico por trade cerrado (entry/exit ref+exec, fees, slippage, net,
  holding; NEW preserva trigger tss, MFE/MAE, stop/target y versiones)
- summary comparable OLD/NEW con identidades (code_git_sha, dataset id/sha, ventana,
  candle/signal hash, versiones, fee/slippage bps, stop/target/trailing, summary_sha256,
  trade_ledger_sha256) y metricas con definicion unica
- MAX_DRAWDOWN_BASIS=REALIZED_CLOSED_TRADES (curva de equity realizada por cierre);
  final_equity realized-only (sin mezclar mark-to-market)
- --output-dir con escritura atomica .part->verify->rename; mismo contenido SKIP,
  distinto FAIL CLOSED (ArtifactConflictError)
- +15 tests harness (25 total): streaming, ledger, metricas, atomicidad/idempotencia,
  conflicto, determinismo; runner 69%->75%
- smoke 3 dias OLDx3/NEWx3 determinista, SKIP, conflicto FAIL y paridad PASS;
  ledger M7 fixed byte-identico (6d64b62b...); paper/certification/wf/holdout intactos
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

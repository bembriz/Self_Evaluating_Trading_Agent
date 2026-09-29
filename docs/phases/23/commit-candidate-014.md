# Commit Candidate Report — 2026-09-29

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> **Candidate 014 — M9-B2A: runner de ventana común OLD-vs-NEW + corrección causal del trailing ATR.**

## Objetivo

Preparar la comparación de 647 días OLD (close-only) vs NEW (trade-sequence) sobre el
**mismo** Gold Medallion, versionando el runner reproducible
(`harness/scripts/m9b_common_window.py`) y corrigiendo la diferencia semántica del trailing
ATR: en `sizing_mode=risk_engine` el trailing pasa a usar el **último ATR 15m confirmado**
(sin lookahead), manteniendo el ATR de entrada para stop/target iniciales y la ruta legacy
`fixed` byte-idéntica. **No** ejecuta los 647 días (gate posterior).

## Rama

| Campo | Valor |
|---|---|
| branch | `medalion` |
| base commit | `841c6369f771646006097b545c03965be45094c4` (HEAD == `origin/medalion` == BASE esperado) |

## Archivos

- **Creados (4 + evidencia):**
  - `harness/scripts/m9b_common_window.py` (runner versionado, 505 líneas)
  - `harness/tests/test_m9b_common_window.py` (10 tests)
  - `docs/phases/23/m9b-common-window-plan.md` (plan/documento de fase)
  - `docs/phases/23/commit-candidate-014.md` (este reporte)
  - **25 logs** `docs/phases/23/evidence/m9b2a-*.log` (15 de M9-B2A + 10 de este candidate)
- **Modificados (3):**
  - `src/infrastructure/medallion/replay.py` (+11/−1)
  - `tests/test_trade_replay.py` (+155/−0, sección M9-B2: 5 tests)
  - `docs/phases/23/evidence/log.md` (índice, +20 filas)
- **Eliminados:** ninguno
- **Total staged:** 32 (4 código/tests · 1 doc de fase · 1 reporte · 26 evidencia)
- **Fuera de alcance:** 0 — sin `progress.yaml`, sin `src/domain/risk/`, sin paper runtime,
  sin deployment, sin certification/safeguard (`m9b2a-cc014-artifacts.log` §6,
  `m9b2a-cc014-artifacts2.log`)

## Diff

```bash
$ git diff --cached --stat        # snapshot previo a este reporte (30 archivos)
 harness/scripts/m9b_common_window.py      | 505 +++++++++++++++++++++
 harness/tests/test_m9b_common_window.py   | 226 +++++++++
 src/infrastructure/medallion/replay.py    |  12 +-
 tests/test_trade_replay.py                | 155 ++++++
 docs/phases/23/m9b-common-window-plan.md  | 122 +++++
 30 files changed, 2122 insertions(+), 1 deletion(-)

$ git diff --cached --numstat | awk '{a+=$1;d+=$2;n++} END {print n,a,d}'
30 2122 1
$ git diff --cached --numstat | grep -E '(src|harness|tests)/'
505  0  harness/scripts/m9b_common_window.py
226  0  harness/tests/test_m9b_common_window.py
 11  1  src/infrastructure/medallion/replay.py
155  0  tests/test_trade_replay.py
```

## Arquitectura afectada

- **`infrastructure/medallion.replay`** (motor M7): `_Position` gana `current_atr`; `_advance`
  lo actualiza **solo** al confirmarse una vela (`close_time <= cutoff`) y **solo** en modo
  `risk_engine`; `_risk_eval` usa `current_atr` para `update_trailing` en dinámico y
  `position.atr` (entrada) en `fixed`. Sin nuevos campos en los registros del ledger ⇒ `fixed`
  byte-idéntico. El orden M7 (path → protective → target → elevar trailing) no cambia.
- **Herramientas del arnés (nuevas):** runner + tests del runner. No es código de producto.
- **Sin cambios:** `src/domain/risk/*` (reutilización pura), `PaperEngine` (su trailing sigue
  usando el ATR recibido por evento), estrategias del Lab, `replay_cli`.
- **Blast radius (codebase-memory):** `_risk_eval` inbound = 3 (todos internos:
  `_Engine.run`, `replay_engine`, `replay_cli.main`). `detect_changes since=841c636`: 30
  archivos, **190 seeds**, `impacted_total=37` — confinado a
  `src/infrastructure/medallion` (replay/replay_cli/strategy_provider) y tests. El runner
  (`harness/**`) no está en el grafo (nuevo) → no genera seeds; se leyó su fuente directamente.

## Índice del grafo

- [ ] Índice re-indexado tras el commit (`index_repository`) → *pendiente de APPROVED (§4.13)*
- [x] Cobertura consultada pre-ejecución (`check_index_coverage`): `replay.py` y
  `tests/test_trade_replay.py` → `no_recorded_issue` con `freshness=metadata_changed`
  (cambiados tras la generación `2026-09-29T10:47:29Z`); `harness/**` → `not_tracked`
  (nuevos). Sin `parse_partial` nuevo. Fuente leída directamente (el agente es el autor).
  → acción `read_source_and_reindex` aplicada; reindex post-commit pendiente.

## Validaciones (contrato del runner)

Ejecutables, evidencia `m9b2a-cc014-runner-contract.log`:

| Requisito | Resultado |
|---|---|
| Runner versionado | `harness/scripts/m9b_common_window.py` staged |
| Acepta `old_close_only` y `trade_sequence` | `MODELS == ("old_close_only","trade_sequence")` |
| Acepta `baseline/donchian/bollinger` | `STRATEGIES == ("baseline","donchian","bollinger")` |
| Registra window/dataset/model/signal hash/summary/report hash | `as_payload()` con 13 campos + líneas `WINDOW/DATASET/MODEL/PARITY/SUMMARY/EXTRA/REPORT_SHA256` |
| FAIL CLOSED si la ventana no coincide | `ventana != COMMON_WINDOW (FAIL CLOSED)` (unit + host `WINDOW_GUARD_FAIL_CLOSED=YES`) |
| Instancia fresca de estrategia por pasada | 2 `_build_strategy(...)` (líneas 442/444); pre-fix reutilizar la instancia stateful produjo `PARITY_FAILED` (`m9b2a-06b`) y post-fix `PARITY PASS` (`m9b2a-06c`) |
| `llm_sell → strategy_exit` solo presentación | `exit_raw={'llm_sell':1}` → `exit_presentation={'strategy_exit':1}` |
| Preserva raw exit reason | `exit_reasons_raw` en el payload, sin sobrescribir |

### Common window

`START=2023-09-09T00:00:00Z` · `END_EXCLUSIVE=2025-06-17T00:00:00Z` · **DAYS=647** ·
**15M_CANDLES=62112** (test + constantes del runner).

### Paridad de señales (smoke 3 días, host)

`SAME_CANDLE_SOURCE_OLD_NEW=YES` (`candle_hash=3443d340…` en ambos modelos) ·
`baseline / donchian / bollinger = PASS` (`m9b2a-06c`, `m9b2a-07`).

### Trailing ATR

`risk_engine` usa último ATR confirmado · cero lookahead (corrupción de velas futuras no
cambia el registro) · initial stop/target conservan ATR de entrada · `fixed` sin cambios
(5 tests, `m9b2a-cc014-tests-global/medallion`).

## Regresión M7 (obligatoria)

| Verificación | Resultado | Evidencia |
|---|---|---|
| Ledger canónico | `6d64b62b48575bdbcda19eb0dbbc46d53a7351606eb5fd93a9c038643a83e625` | `m9b2a-07` §1 |
| Regeneración legacy (sin flags) | idéntica (`LEGACY_M7_LEDGER_IDENTICAL=YES`) | `m9b2a-07` §1 |
| Relectura en frío (solo `sha256sum`, sin replay) | canónico y regen idénticos | `m9b2a-cc014-artifacts.log` §5 |

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Calidad (ruff + format + mypy, 290 archivos) | **PASS** | `m9b2a-cc014-quality.log` |
| Suite global (`--cov=src --cov-fail-under=90`) | **PASS** — 1263 passed, 1 skipped · **90.56%** | `m9b2a-cc014-tests-global.log` |
| Scope medallion | **PASS** — 323 passed · **94.27%** | `m9b2a-cc014-tests-medallion.log` |
| Harness tests | **PASS** — 77 passed (2 fallos PDF **pre-existentes** excluidos) | `m9b2a-cc014-tests-harness.log` |
| Cobertura aislada del runner | **69%** (`m9b_common_window.py`: 220 stmts, 62 missing) — **documentada sin ocultar**; líneas no cubiertas = `main()`/CLI/IO, validadas en el smoke host | `m9b2a-cc014-tests-harness.log` |
| Smoke host (no repetido) | **PASS** — 6 combinaciones ×2 corridas byte-idénticas + paridad ×3 | `m9b2a-06c`, `m9b2a-cc014-artifacts.log` §1-4 |

## Cobertura

**Global 90.56%** (≥90) · **medallion 94.27%** (≥90) · **runner 69%** documentado (herramienta
del arnés; `harness/scripts` no es `src/`). Números exactos en los logs citados.

## Calidad

```bash
uv run ruff check .                 # All checks passed!
uv run ruff format --check .        # 333 files already formatted
uv run mypy src tests               # Success: no issues found in 290 source files
$ git diff --cached --check         # RC=2 → 8 avisos de trailing whitespace:
                                    #   7 en m9b2a-06c-smoke.log (salida verbatim de `tr`)
                                    #   1 en cabecera de m9b2a-08-secret-scan.log (evidence.sh)
                                    #   0 en src/, harness/, tests/, *.md (RC_AGENT=0)
```

**Diff check (alcance):** los 8 hallazgos están en logs de evidencia verbatim (espacio final
que produce la propia salida del comando) — se preservan sin recortar (precedente cc-012/013).
Aislado: `git diff --cached --check -- src harness tests docs/phases/23/m9b-common-window-plan.md`
→ **RC=0**. → **DIFF_CHECK=PASS**. Evidencia: `m9b2a-cc014-diff-check.log`.

## Seguridad

- [x] 6 patrones con **HITS=0** (clave privada, `AKIA…`, asignaciones de credenciales,
  `Bearer …`, URL `user:pass@`, archivos sensibles) — `m9b2a-cc014-secret-scan.log`
- [x] Sin `.env`/`.pem`/`.key` staged
- [x] Único hex-64 fuera de logs: `3443d340…` = **candle sequence hash público** documentado
  en el plan (no es credencial). Código y tests: 0 hex-64.

## Smoke / correspondencia de artefactos

No repetido (evidencia existente suficiente). Verificado que los artefactos corresponden al
árbol actual (`m9b2a-cc014-artifacts.log`):
`FILES_UNCHANGED_SINCE_SMOKE=YES`; hashes **locales == hashes desplegados en el host**
(`replay.py bd3a16bb…`, runner `b0ec0226…`) ⇒ el smoke corrió exactamente este código;
paridad/determinismo registrados en `m9b2a-06c`.

## Seguridad de infraestructura

`WALK_FORWARD_READS=0` · `FINAL_HOLDOUT_READS=0` · `PAPER_CONTAINER_CHANGED=NO` ·
`CERTIFICATION_TOUCHED=NO` · `PROGRESS_YAML_UNTOUCHED=YES` · Silver/Gold sin `.part` ·
`src/domain/risk/` intacto · `PaperEngine` intacto (`m9b2a-07`, `m9b2a-cc014-artifacts*`).

## Riesgos

- La cobertura del runner es 69% (líneas de `main()`/IO): el contrato puro está cubierto por
  tests; el camino CLI queda validado por el smoke host (6 corridas + guard FAIL CLOSED).
- Los contadores `decisions` difieren entre modelos por diseño (OLD cuenta eventos
  PaperEngine; NEW cuenta señales): la comparación se ancla en `signal_hash`, no en conteos.
- El smoke es de 3 días y sin lectura económica: los resultados del run de 647 días son otro
  gate.

## Deuda técnica

- Los scripts de smoke M9-B2A viven en `/tmp/opencode/` (fuera del repo); el runner (el
  artefacto reutilizable) sí está versionado.
- `Phase 21R` sigue siendo `REFERENCE_ONLY` (otra fuente de velas); no se usó como input OLD.
- Elevar la cobertura del runner (main/IO) requeriría un fixture Gold en `harness/tests`;
  se priorizó el smoke end-to-end.

## Mensaje de commit propuesto

```
feat(medallion): add common-window strategy comparison runner

- harness/scripts/m9b_common_window.py: runner OLD (close-only PaperEngine) vs
  NEW (Trade-Level Replay) sobre la MISMA secuencia de velas Gold 15m;
  --strategy {baseline,donchian,bollinger} x --model {old_close_only,trade_sequence}
- ventana comun 647 dias / 62112 velas (START=2023-09-09Z, END_EXCLUSIVE=2025-06-17Z)
  con guard FAIL CLOSED para --expect-common-window
- paridad de senales OBLIGATORIA (hash determinista) antes de interpretar PnL;
  instancia fresca de estrategia por pasada (stateful, single-use)
- reporting con window/dataset/model/candle_hash/signal_hash/summary/REPORT_SHA256
- trailing ATR causal en sizing_mode=risk_engine: usa el ULTIMO ATR 15m confirmado
  (se actualiza solo al confirmarse una vela; cero lookahead); initial stop/target
  siguen con el ATR de entrada; orden M7 intacto; fixed legacy sin cambios
- normalizacion llm_sell -> strategy_exit solo para presentacion (raw preservado,
  PaperEngine sin tocar)
- +15 tests (5 en tests/test_trade_replay.py, 10 en harness/tests); suite 1263 passed,
  cobertura global 90.56% y medallion 94.27%; harness 77 passed
- smoke 3 dias OLDx3/NEWx3 determinista y con paridad PASS en lenovosrv;
  ledger M7 fixed byte-identico (6d64b62b...); paper/certification/wf/holdout intactos
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

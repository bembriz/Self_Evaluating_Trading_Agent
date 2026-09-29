# Commit Candidate Report — 2026-09-29

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> **Candidate 013 — M9-B1: integración StrategyDecisionProvider + RiskEngine dynamic sizing (código + tests + docs/evidencia).**

## Objetivo

Integrar las tres estrategias congeladas del Lab (`EmaRsiBaseline`,
`EthDonchianBreakout`, `EthBollingerMeanReversion`) con el Trade-Level Replay M7 mediante
el adaptador `StrategyDecisionProvider` y **sizing dinámico opt-in** vía `RiskEngine`
(escenario Phase 22B explícito `m9b-22b-parity-v1`), manteniendo la ruta legacy
`scripted`/`fixed` **byte-idéntica** al UAT M7 (sha
`6d64b62b48575bdbcda19eb0dbbc46d53a7351606eb5fd93a9c038643a83e625` verificado en frío
durante este candidate). Cierra la validación M9-B1 (smoke 3 días, 3 estrategias,
2 corridas) sin ejecutar FULL DEVELOPMENT.

## Rama

| Campo | Valor |
|---|---|
| branch | `medalion` |
| base commit | `5dbc1c3c871a743cd0a54274fcc4fdce18e54d1f` (HEAD == `origin/medalion` == BASE esperado) |

## Archivos

- **Creados (5 + evidencia):**
  - `src/infrastructure/medallion/strategy_provider.py` (adaptador fail-closed)
  - `tests/test_strategy_provider.py` (16 tests)
  - `tests/test_strategy_replay_no_lookahead.py` (3 tests)
  - `docs/phases/23/m9b-strategy-replay-plan.md` (plan M9-B0 aprobado)
  - `docs/phases/23/m9b-strategy-replay.md` (informe de ejecución M9-B1)
  - `docs/phases/23/commit-candidate-013.md` (este reporte)
  - **16 logs** de evidencia M9-B (`m9b-01..m9b-10` con variantes b/c) + **8 logs**
    de este candidate (`m9b-cc013-*`: quality, tests-global, tests-medallion,
    artifacts-tree, diff-check, diff-check-final, secret-scan, staged-final)
- **Modificados (4):**
  - `src/infrastructure/medallion/replay.py` (+131/−6)
  - `src/infrastructure/medallion/replay_cli.py` (+98/−5)
  - `tests/test_trade_replay.py` (+266/−0)
  - `docs/phases/23/evidence/log.md` (índice, +25 filas)
- **Eliminados:** ninguno
- **Total staged:** 34 (6 de código/tests · 2 docs de fase · 1 reporte · 25 evidencia)
- **Fuera de alcance:** 0 — sin `progress.yaml`, sin `src/domain/risk/`, sin paper
  runtime, sin deployment, sin certification/safeguard (ver `m9b-10-repo-safety.log`
  y `m9b-cc013-artifacts-tree.log` §6)

## Diff

```bash
$ git diff --cached --stat          # snapshot previo a este reporte (25 archivos)
 .../m9b-strategy-replay.md              | 117 ++++++++
 src/infrastructure/medallion/replay.py  | 131 +++++++-
 src/infrastructure/medallion/replay_cli.py | 98 +++++-
 src/infrastructure/medallion/strategy_provider.py | 125 ++++++++
 tests/test_strategy_provider.py         | 333 +++++++++++++++++++++
 tests/test_strategy_replay_no_lookahead.py | 143 +++++++++
 tests/test_trade_replay.py              | 266 ++++++++++++++++
 25 files changed, 2087 insertions(+), 11 deletions(-)

$ git diff --cached --numstat | awk '{a+=$1;d+=$2;n++} END {print n,a,d}'
25 2087 11
```

> Snapshot de staging: evidencia `m9b-cc013-staged-final.log` (33 archivos al momento de
> su registro; el total final es **34** = 33 + `m9b-cc013-diff-check-final.log` +
> su fila del índice).

## Arquitectura afectada

- **`infrastructure/medallion` (replay stack)** — único módulo tocado:
  - `replay.py`: `ReplayScenario(+sizing_mode, +intensity, __post_init__ FAIL CLOSED)`,
    `ReplayResult(+rejected_reasons)`, `_Engine` con estado de portfolio **solo** en modo
    dinámico (`_evaluate_risk`, `_roll_day`, `_open_position(verdict)`), meta del ledger
    con claves de auditoría **solo** `sizing_mode != "fixed"`.
  - `replay_cli.py`: flags `--strategy`/`--sizing-mode`, `_m9b_scenario` (22B explícito),
    `_build_strategy` (composition root, import diferido de `lab`), línea `SIZING=`
    exclusiva del modo dinámico (stdout legacy intacto).
  - `strategy_provider.py` (**nuevo**): `StrategyDecisionProvider` (Protocol
    `DecisionProvider`) + `rows_to_domain_candles`; consume
    `domain.trading.strategy.Strategy` sin tocarlo.
- **Dominio intacto:** `src/domain/risk/` sin cambios (reutilización pura de
  `RiskEngine/RiskConfig/stops/sizing/guards`); las 3 estrategias del Lab sin cambios.
- **Nuevo acople:** `medallion.replay._Engine → RiskEngine.evaluate` (solo cuando
  `sizing_mode == "risk_engine"`). En modo `fixed` el motor **no** instancia `RiskEngine`
  (cubierto por test spy: `legacy_fixed_sizing_bypasses_risk_engine`).
- **Consumidores aguas abajo sin cambios:** `replay_cli` y tests son los únicos
  consumidores del módulo `replay` (ver blast radius).

## Índice del grafo

- [ ] Índice re-indexado tras el commit (`index_repository`) → *pendiente de APPROVED (§4.13)*
- [x] Cobertura verificada sobre archivos tocados (`check_index_coverage`) → **6/6
  `no_recorded_issue` + `metadata_match`** (generación `2026-09-29T10:35:25Z`)
- **Incidente y resolución:** el índice preexistente estaba **obsoleto** (generación
  `2026-09-28T06:01:58Z`, anterior a M7: `replay_engine` no existía en el grafo pese a
  `head_sha=5dbc1c3` en los metadatos). Re-indexado `full` durante este candidate:
  **21128 nodos / 48874 aristas**; se eliminó un proyecto duplicado creado por nombre
  derivado (`home-xuum-Documentos-proyectos-Self-Evaluating_Trading_Agent` → `deleted`).
- **Blast radius** (`detect_changes since=5dbc1c3`, working tree): 31 changed files,
  **245 seed symbols**, `impacted_total=3` → `src/infrastructure/medallion` (módulos
  `replay`, `replay_cli`) + `tests/test_trade_replay.py`; **sin impacto transverso**.
- **`RiskEngine.evaluate` inbound (24 callers):** incluye el nuevo
  `medallion.replay._Engine` (`_evaluate_risk`, `_drain_decisions`, `run`); el resto
  (PaperEngine/PaperRunner/paper_session CLI/LabSessionRunner/harness `phase18b..20b`
  scripts) **sin cambios** — la mutación solo añade un caller, no altera el módulo.

## Tests ejecutados

| Suite / verificación | Resultado | Evidencia |
|---|---|---|
| Calidad (ruff check + format + mypy, 290 archivos) | **PASS** (0 errores) | `m9b-cc013-quality.log` |
| Suite completa `pytest --ignore=tests/integration --cov=src --cov-branch --cov-fail-under=90` | **PASS** — **1258 passed, 1 skipped** (≥ resultado M9-B1: 1258) | `m9b-cc013-tests-global.log` |
| Scope medallion (10 suites, `--cov=infrastructure.medallion --cov-fail-under=90`) | **PASS** — **318 passed** | `m9b-cc013-tests-medallion.log` |
| StrategyDecisionProvider (mapeo/timestamps/FAIL CLOSED) | **PASS** (16 tests) | `m9b-01/02` + `m9b-cc013-*` |
| Signal parity adapter vs `on_candle` (baseline/donchian/bollinger) | **PASS** (3 tests) | ídem |
| No-lookahead (corruptor de prefijo ×3 + contexto + determinismo) | **PASS** (3 tests) | ídem |
| Dynamic sizing / stop base reference / estado entre round-trips / rechazo | **PASS** | ídem |
| Legacy fixed bypass de RiskEngine (spy `instances==[]`) | **PASS** | ídem |
| CLI (`--strategy`, `--sizing-mode`, defaults, legacy, exit 2) | **PASS** (5 tests) | ídem |
| Smoke host M9-B (3 estrategias × 2 corridas + verify) | **PASS** (no repetido; correspondencia verificada) | `m9b-07/08/09c` + `m9b-cc013-artifacts-tree.log` |
| Regresión M7 ledger (sha en frío, solo lectura en lenovosrv) | **PASS** — `6d64b62b…` idéntico | `m9b-cc013-artifacts-tree.log` §4-5 |

### Validaciones de diseño (requeridas por M9-B1)

| Requisito | Verificación | Evidencia |
|---|---|---|
| Risk eval en primer trade elegible, antes de abrir | orden `advance→fill_pending_exit→drain→evaluate→open` + unit | `m9b-strategy-replay.md` §Diseño; tests M9-B |
| `price=reference_price`, `atr=Decision.atr` | unit + host (`ref == close` de la vela de decisión) | `m9b-09c` §1 |
| Stop ATR = 2.0 · Target R = 2.0 · Trailing ATR = 3.0 | aserciones host (`stop==ref−2.0×atr`, `target==ref+2.0×(ref−stop)`) + deploy (`trailing==3.0`) | `m9b-09c` §1, `m9b-06b` |
| Fee = 10 bps · Slippage = 2 bps · intensity MEDIUM | escenario `m9b-22b-parity-v1` + stdout `SIZING=… intensity=medium` | `m9b-06b`, `m9b-07/08` |
| Dynamic sizing opt-in · legacy fixed intacto | meta condicional + meta legacy 21 claves + spy test | `m9b-09c` §1, unit |
| `decisions_rejected` + motivos auditables | meta dinámica `decisions_rejected`/`rejected_reasons` | `m9b-09c` §1 (0 rechazos en ventana; ruta cubierta por unit `max_drawdown=0.0`) |

## Cobertura

- **Global (branch):** **90.55%** (`--cov-fail-under=90` → PASS)
- **Scope `infrastructure.medallion` (branch):** **94.25%** (replay.py **91%**,
  replay_cli **91%**, strategy_provider **91%**)
- Exactos en `m9b-cc013-tests-global.log` / `m9b-cc013-tests-medallion.log`.

## Calidad

```bash
uv run ruff check .                 # All checks passed!
uv run ruff format --check .        # 331 files already formatted
uv run mypy src tests               # Success: no issues found in 290 source files
uv run pytest tests --ignore=tests/integration --cov=src --cov-branch --cov-fail-under=90
                                    # 1258 passed, 1 skipped · 90.55%
$ git diff --cached --check         # RC=2 → 8 avisos de "trailing whitespace":
        · 4 filas del índice evidence/log.md generadas por harness/scripts/evidence.sh
        · 4 cabeceras `comando: bash -c ` de logs m9b-cc013-* (comandos multilínea)
        · 0 hallazgos en artefactos escritos por el agente (src/, tests/, *.md) → RC=0
```

**Diff check (alcance y decisión):** los 8 hallazgos están en artefactos de evidencia
generados por `evidence.sh` (cabecera y filas de índice), no en código ni en documentación
escrita a mano. Se preservan **sin editar** por requisito de evidencia auditable
(precedente: `commit-candidate-012.md`, mismo criterio con 168 avisos). Verificado de
forma aislada: `git diff --cached --check -- src tests docs/phases/23/m9b-*.md
docs/phases/23/commit-candidate-013.md` → **RC=0**. → **DIFF_CHECK=PASS** con alcance
documentado. Evidencias: `m9b-cc013-diff-check.log` (snapshot intermedio, RC=0) y
`m9b-cc013-diff-check-final.log` (snapshot final, RC=2 con los 8 avisos clasificados).

## Seguridad

- [x] Sin secretos en el diff — 6 patrones con **HITS=0** (clave privada, `AKIA…`,
  asignaciones de credenciales, `Bearer …`, URL `user:pass@`, archivos `.env/.pem/.key`)
- [x] Sin archivos `.env` ni credenciales staged
- [x] Secret scanning limpio — único patrón con matches: hex-64 fuera de `*.log` →
  **7 líneas**, todas en `m9b-strategy-replay*.md`, clasificadas como **hashes
  SHA-256 públicos por diseño** (2 dataset_ids `gold-replay-…`, sha del ledger M7
  `6d64b62b…`, 3 sha de ledgers dinámicos `52823a0d…/36bbccd4…/05fc6f12…`) — no son
  credenciales. Código fuente y tests: 0 matches.
- Evidencia: `m9b-cc013-secret-scan.log`.

## Smoke / correspondencia de artefactos

No se repitió el smoke (evidencia existente suficiente). Verificación de que los
artefactos registrados corresponden al árbol actual (`m9b-cc013-artifacts-tree.log`):

- `SRC_TEST_UNCHANGED_SINCE_SMOKE=YES` — ningún `src/`/`tests/` con mtime posterior al
  deploy/run1 (`find -newer` vacío) + hashes SHA-256 del árbol actual registrados.
- Lectura **fresca en lenovosrv** (solo `sha256sum`, sin replay):
  legacy canónico = `6d64b62b…` (**regresión NO producida**), `legacy-regen` =
  `6d64b62b…`, run1==run2 de las 3 estrategias = shas registrados en `m9b-08`.
- Worktree solo contiene archivos del alcance esperado.

## Riesgos

- **0 rechazos de RiskEngine en el smoke de 3 días** (`decisions_rejected=0`,
  `rejected_reasons={}`): la ruta de rechazo por drawdown/daily-loss solo está ejercida
  por unit tests (`max_drawdown=0.0` → `{"max_drawdown": 1}`); el comportamiento con
  rechazos reales se verá en M9-B full development.
- Smoke de **mecanismo** sobre 3 días: sin conclusiones de rentabilidad;
  `POPULATIONS_DIRECTLY_COMPARABLE=NO` (diferente estrategia/sizing/riesgo/costes vs
  legacy scripted).
- El grafo se re-indexó con el working tree **sin commitear**: tras APPROVED y commit
  corresponde re-indexar de nuevo (§4.13) para fijar la generación al nuevo HEAD.

## Deuda técnica

- Los scripts de smoke M9-B viven en `/tmp/opencode/m9b-*.sh` (fuera del repo); si se
  reutilizan en M9-B full, versionarlos en `harness/`.
- La verificación de paridad de señales usa fixtures sintéticos construidos para
  provocar señales en las 3 estrategias; ampliar con tramos reales en full development.
- `max_time_in_position` sigue en el catálogo sin implementar (herencia M7, sin cambios).

## Mensaje de commit propuesto

```
feat(medallion): integrate real strategies with trade-level replay

- StrategyDecisionProvider: adaptador fail-closed (decision_ts==close_time,
  signal_ts:=close_time, orden estricto de candle_index, HOLD/BUY/SELL)
- sizing dinámico opt-in (sizing_mode=risk_engine): RiskEngine.evaluate en el
  primer trade elegible con price=reference_price; stop/target/quantity del
  veredicto (stop=ref-2*ATR, target=ref+2R, trailing 3*ATR, fee 10bps, slip 2bps,
  medium); estado de portfolio y decisiones_rejected auditables solo en modo dinámico
- replay_cli: --strategy {scripted,ema-rsi,donchian,bollinger} y
  --sizing-mode {fixed,risk_engine}; escenario explicito m9b-22b-parity-v1;
  stdout legacy byte-idéntico en la ruta scripted/fixed
- meta del ledger con claves de auditoría solo cuando sizing_mode != fixed:
  ledger M7 scripted regenerado sha==6d64b62b48575bdbcda19eb0dbbc46d53a7351606eb5fd93a9c038643a83e625
- +31 tests (paridad x3, no-lookahead x3, sizing/estado/rechazo, meta condicional, CLI);
  suite 1258 passed; coverage global 90.55% y medallion 94.25%; ruff/format/mypy limpios
- smoke 3 dias x3 estrategias x2 corridas deterministas en lenovosrv
  (/srv/fast/medallion/m9b-work); paper-runner, certification, wf/holdout intactos
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

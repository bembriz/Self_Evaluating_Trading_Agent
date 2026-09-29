# M10 — Candidato de integración a `main` (Fase 23 · Medallion)

**Fecha:** 2026-09-29 (UTC-6)
**Rama origen:** `medalion` @ `a26f3eaa804af4266f60483a9b21f20a01d5c2a4`
**Rama destino:** `main` @ `962c971249fd34671d0ace323100aac984fd44ff` (= `origin/main`)
**Naturaleza:** informe **read-only**. **NO** se ha hecho merge/commit/push. `main` sin modificar.
**Gate humano requerido antes de integrar** (PRD §64-66; AGENTS §7).

---

## 1. Viabilidad de integración

| Comprobación | Resultado |
|---|---|
| `git merge-base --is-ancestor main HEAD` | **SÍ** |
| Commits `main..HEAD` | **18** |
| Divergencia (`git rev-list --count main..HEAD` / `HEAD..main`) | `18 / 0` |
| Tipo de integración | **Fast-forward** (sin merge commit, sin conflictos) |
| `main` == `origin/main` | **SÍ** (`962c9712…`) |
| `main` modificado durante M10 | **NO** |

## 2. Commits incluidos (`git log --oneline main..HEAD`)

```text
a26f3ea docs(progress): mark M9 strategy validation done
b3bb963 docs(medallion): record M9-B full development review
fcba380 feat(medallion): harden common-window full replay
c3bb67d feat(medallion): add common-window strategy comparison runner
841c636 feat(medallion): integrate real strategies with trade-level replay
5dbc1c3 docs(medallion): record M9-A full DEVELOPMENT dataset
4fd6b4c feat(medallion): M9-A1 Bybit Spot source schema evolution (V1/V2) + metadata backfill
dc5c0a2 feat(medallion): M8 one-shot container deploy on lenovosrv
79b1de5 feat(medallion): M7 two-clock trade-level replay engine
04441ad feat(medallion): M6 immutable Gold replay dataset manifest
37cd798 feat(medallion): M5 deterministic multi-timeframe Silver candles
d2aef30 feat(medallion): M4 canonical deterministic Silver trades
cc6d75f feat(medallion): M3 idempotent Bronze Bybit Spot ingestion
69607b4 docs(phase-23): M2 platform foundation (dirs, platform-net, repo base)
47317b5 docs(phase-23): M1-B storage + M1-C alineación de repos
4d4a9bd docs(phase-23): record GastosIA backup and restore validation
df907c5 docs(phase-23): record lenovosrv infrastructure revalidation
12e988e docs(phase-23): define medallion replay and platform architecture
```

## 3. Diff agregado

```text
402 files changed, 42273 insertions(+), 4 deletions(-)
```

Distribución por área:

| Área | Ficheros | Carácter |
|---|---|---|
| `docs/phases/23/**` + `phase-23-report.md` | 361 | Documentación/evidencia (sin runtime) |
| `src/infrastructure/medallion/**` | 14 | **Nuevo módulo** (aditivo) |
| `tests/**` (medallion) | 8 | Tests nuevos |
| `deployment/medallion/**` | 4 | Dockerfile + compose + README |
| `deployment/platform/**` | 2 | Fundación de plataforma |
| `docs/adr/` | 3 | ADR-0005/0006/0007 |
| `.opencode/skills/` | 3 | `medallion-market-data`, `backtesting`, `bybit-integration` |
| `harness/scripts/m9b_common_window.py` + test | 2 | Runner comparación |
| `AGENTS.md`, `docs/design`, `docs/skill-gap`, `harness/state` | 5 | Gobernanza/estado |

### Código afectado

```text
src/infrastructure/medallion/{__init__,bronze,candles,candles_cli,cli,gold,gold_cli,
                             replay,replay_cli,schema_backfill_cli,silver,silver_cli,
                             split_guard,strategy_provider}.py
harness/scripts/m9b_common_window.py
tests/{test_bronze_ingest,test_gold_dataset,test_silver_candles,test_silver_trades,
       test_source_schema,test_strategy_provider,test_strategy_replay_no_lookahead,
       test_trade_replay}.py
```

## 4. Blast radius (codebase-memory-mcp, gen actual)

- `main` → HEAD: **406 ficheros cambiados**, **1003 seed symbols**, **impacted_total = 70**.
- Los impactados son mayoritariamente **nodos de test** (`tests/lab` 27, `tests/e2e` 8,
  `tests/integration` 4) y **el propio módulo medallion** (`src/infrastructure` 7);
  el resto, `harness/scripts`.
- **Cero** impacto en `src/domain/risk`, `src/application/services/paper_engine.py` ni en
  el runtime de paper/certificación (verificado por diff: `RISK_ENGINE_UNCHANGED=YES`,
  `PAPER_ENGINE_UNCHANGED=YES`, `PAPER_CERT_CODE_CHANGED=NO`).
- El módulo `src/infrastructure/medallion` es **nuevo y additivo**: no reemplaza rutas
  existentes del producto.

## 5. Validación

| Requisito | Resultado | Evidencia |
|---|---|---|
| Suite producto completa | **1263 passed, 1 skipped** | `docs/phases/23/evidence/coverage-src.log` |
| Cobertura `src` (branch) | **90.56%** ≥ 90 | `coverage.json` (regenerado M10) |
| Cobertura medallion (branch) | **94.27%** ≥ 90 (complementaria) | `m9b2b-03-tests-medallion.log` |
| Lint + format | **PASS** | `lint.log` (`exit=0`) |
| Typing | **PASS** | `typing.log` (`exit=0`) |
| Tests arnés | PASS | `m9b2b-04-tests-harness.log` |
| Secret scan `main...HEAD` | **0 hits** (5 patrones + hex-64 en `.py` = 0) | `m10-final-audit.log` |
| No-leakage | `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0`, `HOLDOUT_STATE=PRISTINE` | `m10-final-audit.log` |
| Paper/certificación | `PAPER_CONTAINER_CHANGED=NO`, `CERTIFICATION_TOUCHED=NO` | `m10-final-audit.log` |
| Ledger legacy M7/M8 | `6d64b62b…` intacto | `m10-final-audit.log` |

## 6. Riesgos y deuda

| Riesgo | Severidad | Mitigación / estado |
|---|---|---|
| Código nuevo de replay (641 stmts) | media | 91% cobertura de rama; tests de no-lookahead y determinismo; ledger byte-idéntico M7=M8 |
| Integración de estrategias reales (M9) | media | `DEVELOPMENT_ONLY=YES`; `OOS_CONCLUSION=NO`; sin tocar WF/holdout |
| Migración destructiva de HDD (M1) | alta (histórica) | Ya ejecutada con gate M1 + backup/restore GastosIA verificado; irreversible pero completada |
| Nuevos ficheros de despliegue/compose | baja | Sin daemon, sin puertos, sin secretos; validado en M8 |
| Documentación voluminosa en `docs/phases/23` | baja | No afecta runtime |

**Deuda técnica:** ninguna nueva declarada en M10.

## 7. Recomendación

Integración **por fast-forward** de `medalion` → `main` tras el **gate de Fase 23**
(UAT aprobado + `gate-approve`). Requiere **autorización explícita** del usuario.
No ejecutar merge/push hasta aprobación.

---

```text
INTEGRATION_TYPE=FAST_FORWARD
MAIN_UNMODIFIED=YES
CONFLICTS=NO
TESTS_PASS=YES
COVERAGE_SRC=90.56
SECRET_SCAN_CLEAN=YES
READY_FOR_INTEGRATION_CANDIDATE=YES (pendiente UAT + autorizacion)
```

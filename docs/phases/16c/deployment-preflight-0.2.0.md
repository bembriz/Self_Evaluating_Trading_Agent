# DEPLOYMENT PREFLIGHT 0.2.0 — lenovosrv (modo diagnóstico / read-only)

> **Fecha:** 2026-09-10 · **Ejecutor:** agente OpenCode · **Modo:** diagnóstico, sin cambios productivos.
> **Veredicto:** `DEPLOYMENT_PREFLIGHT_FAIL` / `BLOCKED` (ver §8). El **artefacto de código** está listo;
> los **prerequisites de despliegue/certificación** tienen brechas accionables que deben cerrarse antes del APPLY gate.

## 0. Contexto y aislamiento

| Campo | Valor |
|---|---|
| repo | `bembriz/Self_Evaluating_Trading_Agent` |
| target branch | `feature/phase-08-llm-decision-agent` |
| merged SHA | `8188e8574261febf05875c7ab15da5ff223c3914` (Merge PR #1 `fix/phase-16c-restart-safe`) |
| worktree preflight | `/tmp/opencode/deployment-preflight-0.2.0` (rama `chore/deployment-preflight-0.2.0`, detached del SHA) |
| worktree viejo 16c | **NO usado** (`/tmp/opencode/phase-16c-restart-safe`, prunable) |
| índice codebase-memory | proyecto `deployment-preflight-0.2.0` indexado (moderate) sobre el SHA exacto |

No se ejecutó ningún cambio productivo: sin `alembic upgrade`, sin stop/recreate, sin redeploy,
sin tocar `compose.yaml` productivo, sin crear/resetear `certification-state`, sin drills, sin START, sin tag/release.

---

## 1. Artifact identity — **PASS**

| Check | Requerido | Observado | Evidencia |
|---|---|---|---|
| HEAD | `8188e85…` | `8188e8574261febf05875c7ab15da5ff223c3914` | `git -C <wt> rev-parse HEAD` |
| app version | `0.2.0` | `0.2.0` | `pyproject.toml:3`, `src/version.py:3`, imagen |
| strategy | `baseline-v1` | `baseline-v1` | `src/domain/trading/strategy.py:97` (`EmaRsiBaseline.version`) |
| risk | `risk-v1` | `risk-v1` | `src/domain/risk/config.py:29` (`RiskConfig.version`) |
| fees/slippage | — | `bybit-spot-v1+conservative-v1` | `fees.py:16`, `slippage.py:16` |
| working tree | limpio | limpio (`git status --porcelain` vacío) | — |

---

## 2. lenovosrv actual (read-only) — **capturado**

Acceso: `ssh administrador@192.168.100.24` (sin sudo; sudo pide contraseña, no usada).

### Contenedores / salud
```
self-evaluating-trading-agent-paper-runner-1   self-evaluating-trading-agent-paper-runner   Up 3 days   (created 2026-09-07 01:16:40 UTC)
self-evaluating-trading-agent-postgres-1       pgvector/pgvector:pg16                       Up 8 days (healthy)   127.0.0.1:5433->5432
```
- `paper-runner` desplegado: **0.1.3** (`/app/src/version.py` dentro del contenedor).
- Imagen prod: `self-evaluating-trading-agent-paper-runner:latest` digest **`sha256:75f41313f8fd851e4c1f4775df25331aa68d936e67f3999f835e48806df76a67`**.
- `/metrics` interno responde **HTTP 200** (`seta_errors_total{kind="ws"}=11`, `seta_reconnects_total=11`).
- **Prometheus y Grafana NO están corriendo** (solo postgres + paper-runner).
- **Anomalía:** `docker logs paper-runner` = **0 líneas** pese a 3 días up (stdout no capturado). Verificar driver/rotación en APPLY.

### PostgreSQL / Alembic
- Accesible (`psql` OK). `alembic_version = 0008_paper_trading_events`.
- `paper_trade_events`: 819 filas, último `timestamp_ms=1789049700000` → **2026-09-10 14:15:00 UTC** (fresco).
- `market_candles`: 0 filas (esperado en 0.1.3, que no persiste velas paper-live).

### Recursos
- Disco `/`: 455G, **4% usado**, 419G libres. `/mnt/warehouse`: 53% usado.
- Memoria: 31Gi total, **29Gi disponibles**. Load 0.07. Sin presión.

### Volúmenes persistentes
- `self-evaluating-trading-agent_pgdata` (named volume) → persistente.
- Bind mounts prod: `/srv/docker/self-evaluating-trading-agent/{reports,certification}`.
- **`promdata` / `grafanadata` NO existen** (Prometheus/Grafana nunca levantados).

### certification-state actual
- Ruta prod: `/srv/docker/self-evaluating-trading-agent/certification/certification-state.json`.
- **Formato legacy v1** (sin `schema_version`): `application_version=0.1.3`, `calendar_days=4`,
  `certification_started_at=2026-09-07T01:16:32Z`, `trade_count=4`, `pnl_pct=-0.00027`.
- **Paper NO CERTIFIED** (4 días < 30; además formato legacy).
- Ya existen snapshots archivados: `certification-state-INVALIDATED-2026-09-02-2026-09-06.json`,
  `certification-state-INVALIDATED-pre-0.1.1.json`.

### Exposición
- Único listener host relevante: `127.0.0.1:5433`. **Sin exposición pública** de 9090/3000/8000.
- `ufw status` **no verificable sin sudo** (queda pendiente de confirmar en APPLY).

---

## 3. Migraciones — **PASS** (validado offline, sin ejecutar en prod)

Cadena: `0001 → 0002 → 0003 → 0004 → 0008 → 0009 → 0010 → 0011` (no existen 0005–0007; salto 0004→0008 es intencional).
Head único: `0011_paper_events_context`.

| Paso | Estado | Evidencia |
|---|---|---|
| Faltantes prod (0008) → head | **0009, 0010, 0011** | `alembic_version=0008_paper_trading_events` |
| Upgrade path `0008→0011` | **PASS** (SQL offline) | `alembic upgrade 0008:0011 --sql` (ALTER market_candles + índices parciales; UNIQUE idempotencia; ADD `decision_context JSONB`) |
| Rollback `0011→0008` | **PASS** (SQL offline) | `alembic downgrade 0011:0008 --sql` (drop columna/constraint/índices; restaura UNIQUE original) |

Migración productiva **NO ejecutada** (correcto).

---

## 4. Imagen 0.2.0 — **PASS** (candidato construido, no desplegado)

| Campo | Valor |
|---|---|
| tag | `seta-paper-runner:0.2.0-preflight` |
| **digest real** | **`sha256:b9917613b26052445b272e73f8507990615a58c7087264ac49525ede782daf4e`** |
| app dentro de imagen | `0.2.0` |
| strategy/risk dentro | `baseline-v1` / `risk-v1` (+ `bybit-spot-v1+conservative-v1`) |
| migraciones dentro | 0001–0011 presentes; `alembic heads` = `0011_paper_events_context` |
| labels | `null` (sin `git_commit` baked) |
| `/app/docs` | **ausente** (el path por defecto de safeguard no es resoluble dentro de la imagen) |

> El digest anterior es de un build **local candidato**; el digest definitivo debe capturarse en el APPLY
> sobre el build que realmente se despliegue (los builds no son bit-reproducibles por timestamps).

---

## 5. Compose / Prometheus — **PASS** (config válida) con notas

`docker compose config -q` → **exit 0** (worktree 0.2.0).

| Check | Requerido | Observado |
|---|---|---|
| retention | ≥45d | `--storage.tsdb.retention.time=${PROMETHEUS_RETENTION:-45d}` → **45d** |
| target paper-runner | `paper-runner:9090` | presente en `deploy/prometheus.yml` |
| volumen persistente | sí | `promdata:/prometheus` (named volume) |
| exposición | no pública | prometheus `127.0.0.1:9090`, grafana `127.0.0.1:3000`, paper-runner **sin `ports`** |

**Notas / brechas:**
- Prod `compose.yaml` (0.1.3) **no** tiene el `command` de retention ni el target `paper-runner:9090`
  (el `deploy/prometheus.yml` prod solo tiene `host.docker.internal:8000`). El `compose.yaml` 0.2.0 **sí** los añade.
- `host.docker.internal:8000` en `deploy/prometheus.yml` **no resuelve en Linux** sin
  `extra_hosts: ["host.docker.internal:host-gateway"]` → target caído (no bloqueante; el target relevante es `paper-runner:9090`).
- Imagen `prom/prometheus:v2.53.0` **no está en lenovosrv**; `promdata`/`grafanadata` no existen → requieren pull/creación en APPLY.
- Prod `compose.yaml` fija `PAPER_SESSION_ID=paper-baseline-15m-ethusdt-0.1.3-20260907`, `PAPER_REPORT_INTERVAL_HOURS=6`,
  `PAPER_STALE_TIMEOUT_SECONDS=120`, `STALE_TIMEOUT_SECONDS=10`; el `compose.yaml` 0.2.0 **no** los trae
  (los defaults de `settings.py` cubren stale=120/10 y `paper_max_runtime_days=45`; `PAPER_SESSION_ID` se auto-deriva).

---

## 6. Certification prerequisites — **FAIL / BLOCKED**

| Prerequisite | Estado | Detalle / evidencia |
|---|---|---|
| `git_commit` real | **FALTA** | No hay `GIT_COMMIT` en compose ni `.env` (no existe `.env` en el proyecto prod). `settings.git_commit=""` → START rechazado por identidad incompleta. |
| `docker_image_digest` real | **FALTA** | No hay `DOCKER_IMAGE_DIGEST`. Candidato conocido: `sha256:b9917613…` (a fijar en APPLY). |
| safeguard evidence path | **FALTA** | Default `docs/phases/16/safeguard-evidence.json` → `/app/docs/...` **no existe** en imagen; no hay mount ni `PAPER_SAFEGUARD_EVIDENCE_PATH`; **no hay evidencia de drills en el server**. |
| certification-state v2 persistente | **NO satisfecho** | El fichero legacy existente hace que `_certification_write_kind()` devuelva `"legacy"` ⇒ el runner **seguiría escribiendo legacy, nunca v2**. Debe **archivarse** el legacy en APPLY (patrón ya usado: `*-INVALIDATED-*.json`). |
| START nunca automático | **PASS** | `--start-certification` obligatorio (`paper_runner.py:592-597,544`); sin flag no hay ancla. |
| deploy/restart sin flag ⇒ NOT_STARTED | **PASS (v2)** | Verificado: path ausente → routing `v2`; v2 con `frozen.certification_started_at=null` ⇒ fase `NOT_STARTED`. Con legacy presente queda **bloqueado** hasta archivarlo. |

Comportamiento verificado en el código del SHA exacto:
```
absent      -> v2
legacy flat -> legacy   | phase: NOT_STARTED
v2          -> v2       | phase: RUNNING
v2 NOT_STARTED -> phase: NOT_STARTED
```

Criterios que el evaluador (`harness/scripts/paper_certification.py`) exigirá: `calendar_days ≥ 30`,
`frozen_versions` sin drift, `accounting_residual == 0`, `recovery_integrity`, `market_evidence_complete`,
`state_continuity`, `certification_reports_complete`, `kill_switch_tested`, `daily_loss_tested`,
`unexplained_market_gaps == 0`, `decision_context_coverage ≥ 100%`, `metrics_history_days ≥ 30`,
`critical_errors` ausentes o explicados.

---

## 7. Rollback plan — documentado

| Capa | Rollback | Notas |
|---|---|---|
| **DB** | `alembic downgrade 0011→0008` (offline validado) | 0011/0010/0009 son aditivas/constraints; downgrade drop columnas/índices y restaura UNIQUE original. Hacer **backup lógico** (`pg_dump`) antes del upgrade. |
| **Imagen/contenedor** | Volver a `self-evaluating-trading-agent-paper-runner:latest` (`sha256:75f41313…`) y recrear paper-runner | Mantener la imagen 0.1.3 retaggeada antes del redeploy. |
| **Compose** | Restaurar copia de `/srv/docker/self-evaluating-trading-agent/compose.yaml` + `deploy/` previos | Guardar copia fechada antes de aplicar. |
| **certification-state** | Restaurar `certification-state.json` legacy desde el snapshot archivado | El estado legacy se archiva (no se borra) antes de arrancar v2. |
| **Prometheus/Grafana** | `docker compose stop prometheus grafana` (volúmenes `promdata`/`grafanadata` se conservan) | No afectan al runner. |
| **ABORT criteria** | Abortar y revertir si: `alembic upgrade` falla o deja DB inconsistente; backup no verificable; el runner 0.2.0 no levanta o `/metrics` ≠ 200; `recovery_integrity`/`accounting_residual` FAIL; se detecta exposición pública; cualquier duda de integridad de datos | Revertir en orden inverso (contenedor→compose→DB) y registrar blocker. |

---

## 8. Dry-run del flujo (solo documentado — NO ejecutado)

```
[ ] STOP 0.1.3            docker compose stop paper-runner
[ ] BACKUP/CHECKPOINT     pg_dump + copia de compose.yaml/deploy/ + archivar certification-state legacy
[ ] alembic upgrade 0011  (prod; 0008→0011)  → verificar alembic_version=0011
[ ] DEPLOY 0.2.0          build/pin digest + env GIT_COMMIT/DOCKER_IMAGE_DIGEST/PAPER_SAFEGUARD_EVIDENCE_PATH + up paper-runner
[ ] PROMETHEUS            pull prom/prometheus:v2.53.0 + up prometheus grafana; verificar targets (paper-runner:9090 up)
[ ] RUNTIME VALIDATION    /metrics 200, eventos en DB, logs, sin drift de versión
[ ] SAFEGUARD DRILLS      harness/scripts/safeguard_drill.py --kind kill_switch/daily_loss --git-commit … --docker-image-digest …
[ ] UAT                   checklist HITL (instructivo)
[ ] USER GATE             presentación + decisión
[ ] START Certification   SOLO tras gate: arranque con --start-certification (ancla v2)
```

**Orden correcto confirmado:** deploy → migraciones → observabilidad → runtime validation → drills/UAT → USER GATE → START.
Los 30 días **no** empiezan en el deploy: empiezan en el START explícito (ancla `frozen.certification_started_at`).

---

## 9. Veredicto

```
DEPLOYMENT_PREFLIGHT_FAIL
BLOCKED
```

**Artefacto de código:** listo (identidad PASS, migraciones PASS, imagen candidata PASS, compose PASS).

**Bloqueos a cerrar antes de solicitar el APPLY gate:**
1. **Fijar `GIT_COMMIT=8188e85…` y `DOCKER_IMAGE_DIGEST=sha256:…`** en el entorno del paper-runner (sin ellos START se rechaza).
2. **Configurar y montar la evidencia de safeguards** (`PAPER_SAFEGUARD_EVIDENCE_PATH` + mount) y **ejecutar los drills** (kill_switch + daily_loss) contra el artefacto desplegado.
3. **Archivar el `certification-state.json` legacy** antes de arrancar 0.2.0 (si no, el runner mantiene el escritor legacy y nunca produce v2).
4. **Desplegar Prometheus/Grafana** (pull imagen, crear volúmenes) — prerequisito de OBSERVABILITY (aunque `metrics_history_days` se cubre con el self-scrape del runner).
5. Menores: confirmar `ufw`; revisar `docker logs` vacío; limpiar target `host.docker.internal:8000` o añadir `extra_hosts`.

Solo cuando 1–4 estén resueltos procede: `DEPLOYMENT_PREFLIGHT_PASS` → `READY_FOR_DEPLOYMENT_APPLY_GATE`.

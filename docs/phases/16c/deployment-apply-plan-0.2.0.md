# DEPLOYMENT APPLY PLAN 0.2.0 — lenovosrv (PROPUESTA, no ejecutada)

> **Fecha:** 2026-09-10 · **Estado:** `READY_FOR_USER_COMMIT_GATE`
> **Nada de este documento se ha ejecutado.** Es el plan de aplicación + los cambios de config en el worktree.
> Cierra los blockers del preflight (`deployment-preflight-0.2.0.md`).

## 0. Artefacto e identidad

| Campo | Valor |
|---|---|
| repo / rama destino | `bembriz/Self_Evaluating_Trading_Agent` · `feature/phase-08-llm-decision-agent` |
| base histórica 16c | `8188e8574261febf05875c7ab15da5ff223c3914` (**NO** es la identidad final) |
| `FINAL_DEPLOY_SHA` | `<SHA final integrado tras el merge de ESTOS cambios>` (se captura en el flujo §2) |
| app / strategy / risk | `0.2.0` / `baseline-v1` / `risk-v1` |
| worktree de preparación | `/tmp/opencode/deployment-preflight-0.2.0` (rama `chore/deployment-preflight-0.2.0`) |
| project prod | `/srv/docker/self-evaluating-trading-agent` |
| imagen objetivo | `self-evaluating-trading-agent-paper-runner:0.2.0` |

**Identidad de artefacto = fail-fast, siempre inyectada en el APPLY:**

```yaml
GIT_COMMIT: "${GIT_COMMIT:?GIT_COMMIT is required - inject final deployed SHA}"
DOCKER_IMAGE_DIGEST: "${DOCKER_IMAGE_DIGEST:?DOCKER_IMAGE_DIGEST is required - inject actual deployed image digest}"
```

`GIT_COMMIT` = `FINAL_DEPLOY_SHA`; `DOCKER_IMAGE_DIGEST` = digest real capturado tras el build.
Sin hardcodear ninguno de los dos.

---

## 1. Cambios de configuración (diff propuesto, en worktree, sin commit)

### `compose.yaml`
```diff
   paper-runner:
     build: .
+    image: self-evaluating-trading-agent-paper-runner:${APP_VERSION:-0.2.0}
     environment:
       ...
       PAPER_TIMEFRAME: 15m
+      PAPER_REPORT_INTERVAL_HOURS: ${PAPER_REPORT_INTERVAL_HOURS:-6}
+      PAPER_MAX_RUNTIME_DAYS: ${PAPER_MAX_RUNTIME_DAYS:-45}          # cierra el trap 7d
+      PAPER_SESSION_ID: ${PAPER_SESSION_ID:-paper-baseline-15m-ethusdt-0.2.0}
       PAPER_REPORT_DIR: reports/paper
       PAPER_CERTIFICATION_STATE_PATH: /app/certification/certification-state.json
-      GIT_COMMIT: ${GIT_COMMIT:-8188e857…}
-      DOCKER_IMAGE_DIGEST: "${DOCKER_IMAGE_DIGEST:?…final build}"
+      GIT_COMMIT: "${GIT_COMMIT:?GIT_COMMIT is required - inject final deployed SHA}"
+      DOCKER_IMAGE_DIGEST: "${DOCKER_IMAGE_DIGEST:?DOCKER_IMAGE_DIGEST is required - inject actual deployed image digest}"
+      PAPER_SAFEGUARD_EVIDENCE_PATH: /app/safeguard/safeguard-evidence.json
     volumes:
       - ./reports:/app/reports:rw
       - ./certification:/app/certification:rw
+      - ./safeguard:/app/safeguard:rw
```

### `deploy/prometheus.yml`
```diff
-      - targets: ["host.docker.internal:8000", "paper-runner:9090"]
+      - targets: ["paper-runner:9090"]
```

### `compose.yaml` (Prometheus/Grafana — ya correcto, sin cambio)
- retention `--storage.tsdb.retention.time=${PROMETHEUS_RETENTION:-45d}` ≥45d.
- prometheus `127.0.0.1:9090`, grafana `127.0.0.1:3000` (loopback), paper-runner **sin `ports`**.

### `.env.example`
- `PAPER_MAX_RUNTIME_DAYS=7 → 45`.
- `GIT_COMMIT=` **vacío** (inyección obligatoria; 8188e85… solo base histórica).
- `DOCKER_IMAGE_DIGEST=` vacío; `PAPER_SAFEGUARD_EVIDENCE_PATH`; `PROMETHEUS_RETENTION=45d`.

---

## 2. Pre-APPLY: build SOLO desde commit limpio e integrado

> El artefacto definitivo **nunca** se construye desde un worktree con cambios sin commit.

```text
1. fix config/plan (este worktree)                  ← HECHO (sin commit)
2. Commit Candidate                                  ← docs/phases/16c/commit-candidate-009.md
3. USER GATE (READY_FOR_USER_COMMIT_GATE)
4. git commit  (solo tras aprobación explícita)
5. PR  chore/deployment-preflight-0.2.0 → feature/phase-08-llm-decision-agent
6. CI green (quality + integration + security + docker + harness + diff-check)
7. merge
8. capturar FINAL_DEPLOY_SHA   (SHA del merge)
9. worktree LIMPIO exactamente en FINAL_DEPLOY_SHA   (git status --porcelain vacío)
10. build imagen 0.2.0 desde ese worktree limpio
11. capturar digest real
12. APPLY (§3)
```

Rollback: si CI falla → no merge; si el worktree no está limpio → abortar antes de build.
ABORT: construir desde un árbol sucio, o `src/version.py ≠ 0.2.0` en `FINAL_DEPLOY_SHA`.

---

## 3. APPLY — orden con rollback por paso

> **PREP:** staging del árbol limpio `FINAL_DEPLOY_SHA` en el server, **sin `--delete`** sobre
> `reports/`, `certification/`, `safeguard/` ni datos persistentes.
> ```bash
> rsync -a --exclude '.git' --exclude '.venv' --exclude 'reports' \
>   --exclude 'certification' --exclude 'safeguard' \
>   <worktree-FINAL_DEPLOY_SHA>/ administrador@192.168.100.24:/home/administrador/seta-0.2.0-deploy/
> ```
> Verificar `seta-0.2.0-deploy/src/version.py == 0.2.0`. Rollback: `rm -rf ~/seta-0.2.0-deploy`.
> ABORT si el SHA staged ≠ `FINAL_DEPLOY_SHA`.

### Paso 1 — stop 0.1.3
```bash
cd /srv/docker/self-evaluating-trading-agent
sudo docker compose stop paper-runner
```
- **Verificar:** `docker ps` sin paper-runner; postgres `healthy`.
- **Rollback:** `sudo docker compose start paper-runner`.
- **ABORT:** no para en <60s.

### Paso 2 — backups
```bash
B=~/seta-backups/$(date -u +%Y%m%dT%H%M%SZ)-0.1.3; mkdir -p "$B"
sudo cp -a /srv/docker/self-evaluating-trading-agent/certification "$B/certification"
sudo cp -a /srv/docker/self-evaluating-trading-agent/reports "$B/reports"
docker exec self-evaluating-trading-agent-postgres-1 pg_dump -U trading -d trading_agent -Fc \
  > "$B/trading_agent-0.1.3.dump"
docker tag self-evaluating-trading-agent-paper-runner:latest \
  self-evaluating-trading-agent-paper-runner:0.1.3-rollback
```
- **Verificar:** `pg_restore -l` lista tablas; `docker images` muestra `:0.1.3-rollback`.
- **Rollback:** N/A.
- **ABORT:** dump falla/vacío.

### Paso 3 — build 0.2.0 (árbol limpio `FINAL_DEPLOY_SHA`)
```bash
cd /home/administrador/seta-0.2.0-deploy
sudo docker build -t self-evaluating-trading-agent-paper-runner:0.2.0 .
```
- Se usa `docker build` (no `docker compose build`) para no requerir aún `DOCKER_IMAGE_DIGEST`.
- **Verificar:** exit 0; `docker run --rm <img> python -c "from version import __version__;print(__version__)"` → `0.2.0`.
- **Rollback:** `docker image rm …:0.2.0`.
- **ABORT:** versión interna ≠ 0.2.0 o migraciones ≠ head 0011.

### Paso 4 — capture actual digest
```bash
DIGEST=$(sudo docker inspect --format '{{.Id}}' self-evaluating-trading-agent-paper-runner:0.2.0)
```
- **Verificar:** `sha256:` + 64 hex.
- **ABORT:** formato inválido.

### Paso 5 — instalar config 0.2.0 en producción
```bash
PROJ=/srv/docker/self-evaluating-trading-agent
STAGE=/home/administrador/seta-0.2.0-deploy
# 5a. backup config productiva
C=~/seta-backups/$(date -u +%Y%m%dT%H%M%SZ)-config; mkdir -p "$C"
sudo cp -a "$PROJ/compose.yaml" "$C/" ; sudo cp -a "$PROJ/deploy" "$C/" ; sudo cp -a "$PROJ/.env" "$C/" 2>/dev/null || true
# 5b/5c. instalar compose.yaml + deploy/ 0.2.0 (SIN tocar persistentes)
sudo install -m 0644 "$STAGE/compose.yaml" "$PROJ/compose.yaml"
sudo rm -rf "$PROJ/deploy" && sudo cp -a "$STAGE/deploy" "$PROJ/deploy"
# 5d. crear safeguard + validar permisos
sudo mkdir -p "$PROJ/safeguard"
sudo chown 1000:1000 "$PROJ/safeguard" && sudo chmod 0775 "$PROJ/safeguard"
test -w "$PROJ/safeguard" && ls -ld "$PROJ/safeguard"
# 5e. inyectar identidad
printf 'GIT_COMMIT=%s\nDOCKER_IMAGE_DIGEST=%s\n' "<FINAL_DEPLOY_SHA>" "$DIGEST" | sudo tee "$PROJ/.env" >/dev/null
# 5f. validar EN EL DIRECTORIO PRODUCTIVO (autoritativo, identidad real)
cd "$PROJ"
sudo env GIT_COMMIT="<FINAL_DEPLOY_SHA>" DOCKER_IMAGE_DIGEST="$DIGEST" docker compose config -q && echo CONFIG_OK
```
- **NUNCA `--delete`** sobre `reports/`, `certification/`, `safeguard/`, datos persistentes.
- **Verificar:** `CONFIG_OK`; `deploy/prometheus.yml` target `paper-runner:9090`; `safeguard` escribible.
- **Rollback:** restaurar `$C/compose.yaml`, `$C/deploy`, `$C/.env`.
- **ABORT:** `docker compose config` falla en el directorio productivo.

### Paso 6 — archive legacy certification-state
```bash
sudo mv "$PROJ/certification/certification-state.json" \
        "$PROJ/certification/certification-state-INVALIDATED-pre-0.2.0.json"
```
- **Motivo:** con el legacy presente, el runner escribe en formato `legacy` y **nunca** v2.
- **Verificar:** el path activo no existe; el archivado sí.
- **Rollback:** `mv` inverso.
- **ABORT:** ya existe `*-INVALIDATED-pre-0.2.0.json` (renombrar con timestamp, no sobrescribir).

### Paso 7 — migrate DB 0008→0011
```bash
cd "$PROJ"
sudo docker compose run --rm --no-deps paper-runner alembic upgrade head
docker exec self-evaluating-trading-agent-postgres-1 \
  psql -U trading -d trading_agent -tAc "select version_num from alembic_version;"
```
- **Verificar:** `0011_paper_events_context`; columna `decision_context` existe.
- **Rollback:** `alembic downgrade 0008` (SQL offline validado) + `pg_dump` si hiciera falta.
- **ABORT:** upgrade parcial/fallido.

### Paso 8 — deploy 0.2.0 SIN `--start-certification`
```bash
sudo docker compose up -d --no-build paper-runner
```
- Estado esperado: **v2 NOT_STARTED** (`schema_version:2`, `frozen.certification_started_at: null`).
- **Verificar:** contenedor up con imagen `:0.2.0`; estado NOT_STARTED; `alembic_version=0011`.
- **Rollback:** stop + `docker tag :0.1.3-rollback :latest` + `up -d --no-build`.
- **ABORT:** estado RUNNING (START accidental) o v1/legacy.

### Paso 9 — observability
```bash
sudo docker compose pull prometheus grafana && sudo docker compose up -d prometheus grafana
curl -s http://127.0.0.1:9090/api/v1/targets | python3 -m json.tool   # paper-runner:9090 "up"
```
- **Verificar:** target `up`; retention 45d; 9090/3000 solo loopback.
- **Rollback:** `docker compose stop prometheus grafana` (volúmenes se conservan).
- **ABORT:** target `down` persistente o exposición no-loopback.

### Paso 10 — runtime validation
```bash
docker exec self-evaluating-trading-agent-paper-runner-1 \
  python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:9090/metrics',timeout=3).status)"
docker exec self-evaluating-trading-agent-postgres-1 \
  psql -U trading -d trading_agent -tAc "select count(*), max(timestamp_ms) from paper_trade_events;"
```
- **Verificar:** `/metrics` 200; eventos nuevos; estado v2 NOT_STARTED estable; sin drift; logs presentes.
- **Rollback:** volver al Paso 8 rollback.
- **ABORT:** runner no procesa, recovery roto, `/metrics` ≠ 200.

### Paso 11 — safeguard drills
```bash
uv run python harness/scripts/safeguard_drill.py --kind kill_switch \
  --out /srv/docker/self-evaluating-trading-agent/safeguard/safeguard-evidence.json \
  --git-commit "<FINAL_DEPLOY_SHA>" --docker-image-digest "$DIGEST"
uv run python harness/scripts/safeguard_drill.py --kind daily_loss \
  --out /srv/docker/self-evaluating-trading-agent/safeguard/safeguard-evidence.json \
  --git-commit "<FINAL_DEPLOY_SHA>" --docker-image-digest "$DIGEST"
```
- **Paths exactos:** host `/srv/docker/self-evaluating-trading-agent/safeguard/safeguard-evidence.json`
  → container `/app/safeguard/safeguard-evidence.json`.
- **Verificar:** ambos PASS; `artifact` == `frozen` (5 claves); `steps` == secuencia canónica;
  `docker exec paper-runner test -r /app/safeguard/safeguard-evidence.json`.
- **Rollback:** borrar el fichero (no afecta al runner).
- **ABORT:** cualquier paso FAIL.

### Paso 12 — UAT (HITL)
- Checklist UAT (skill `uat-hitl`); veredicto APPROVED/REJECTED del usuario.
- **ABORT:** UAT REJECTED ⇒ no START.

### Paso 13 — USER GATE
- Presentar evidencia consolidada + UAT; esperar aprobación explícita.

### Paso 14 — explicit START
```bash
cd "$PROJ"
sudo docker compose stop paper-runner
sudo docker compose run --rm --no-deps paper-runner \
  python -m main paper-runner --symbols ETHUSDT --timeframe 15m --start-certification --seconds 30
sudo docker compose up -d --no-build paper-runner
```
- El one-shot ancla el reloj v2 y sale; el servicio normal preserva el ancla (nunca re-ancla).
- **Verificar:** `schema_version:2`, fase RUNNING, `frozen` con las 10 claves y `git_commit=FINAL_DEPLOY_SHA`,
  `docker_image_digest=$DIGEST`.
- **Rollback:** archivar estado anclado y reiniciar certificación (operador).
- **ABORT:** START rechazado o identidad inconsistente.

---

## 4. Validaciones ejecutadas (dry-run, sin cambios productivos)

| Check | Comando | Resultado |
|---|---|---|
| `GIT_COMMIT` missing | `docker compose config -q` (solo digest) | **FAIL** `GIT_COMMIT is required - inject final deployed SHA` |
| `DOCKER_IMAGE_DIGEST` missing | `docker compose config -q` (solo commit) | **FAIL** `DOCKER_IMAGE_DIGEST is required - inject actual deployed image digest` |
| ambos presentes | `docker compose config -q` | **PASS (exit 0)** |
| mount safeguard | render | bind `<proj>/safeguard` → `/app/safeguard` |
| `PAPER_SAFEGUARD_EVIDENCE_PATH` | render | `/app/safeguard/safeguard-evidence.json` |
| Prometheus target | `deploy/prometheus.yml` | `["paper-runner:9090"]` |
| retention | render | `--storage.tsdb.retention.time=45d` |
| exposición | render | prometheus `127.0.0.1:9090`, grafana `127.0.0.1:3000`, paper-runner sin `ports` |
| restart sin START ⇒ NOT_STARTED | `pytest -k "not_started or restart or legacy or certification or start"` | **25 passed, 19 deselected** (`test_periodic_write_without_flag_produces_not_started_v2`, `test_case7_not_started_never_passes`, …) |
| E2E productor→state→evaluador | `pytest tests/e2e/test_certification_state_v2_e2e.py` | **9 passed** |

---

## 5. Criterios ABORT globales

Abortar y revertir en orden inverso si cualquiera:
- build desde árbol sucio / SHA staged ≠ `FINAL_DEPLOY_SHA`.
- `docker compose config` falla en el directorio productivo.
- `pg_dump` no restaurable; `alembic upgrade` parcial (≠ 0011).
- imagen 0.2.0 no arranca o `/metrics ≠ 200`.
- estado RUNNING/legacy antes del START explícito.
- target `paper-runner:9090` `down` o exposición no-loopback.
- drills de safeguard FAIL; UAT REJECTED.

---

## 6. Veredicto

```
READY_FOR_USER_COMMIT_GATE
```

Cambios preparados y validados en el worktree; **no aplicados, no commiteados**.
Próximo paso: aprobación del usuario para el commit (ver `commit-candidate-009.md`).

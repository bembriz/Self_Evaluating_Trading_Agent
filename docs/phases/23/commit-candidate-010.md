# Commit Candidate Report — 2026-09-28 (M8)

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> **Estado: NO COMMIT** — pendiente de aprobación explícita del usuario.

## Objetivo

Registrar M8 (Deploy Medallion en lenovosrv): runtime batch/one-shot desplegado en
`/srv/docker/medallion` con imagen ligada al SHA `79b1de5…` (`ARG GIT_SHA` fail-closed +
`LABEL revision` + `/app/GIT_SHA`), compose con aislamiento verificado
(`network_mode: none`, rootfs `ro`, `cap_drop: ALL`, `no-new-privileges`, canónico `ro`,
NVMe `rw`, marker `ro`, sin puertos/creds/PG/platform-net), UAT con los 5 CLIs dentro del
contenedor y el **mismo escenario scripted de M7** ejecutado en contenedor: ledger
byte-idéntico al de M7 (`6d64b62b…`, 1 880 793 trades, 23 cerrados), rc=0, determinista e
idempotente, canónico y paper-runner intactos, y la marca `23/m8-deploy` = done en el ledger.

## Rama

| Campo | Valor |
|---|---|
| branch | `medalion` |
| base commit | `79b1de5b8fc827397e608b698d315498b36ca92d` (= HEAD verificado en preflight y postcheck) |

## Archivos

- **Creados (21):**
  - `deployment/medallion/Dockerfile` — imagen one-shot `python:3.12-slim`, `ARG GIT_SHA`
    fail-closed (40 hex), `LABEL org.opencontainers.image.revision`, `ENV MEDALLION_GIT_SHA`,
    `/app/GIT_SHA` (0444), `COPY src`, `USER 1000:1000`, CMD `replay_cli --help`; sin pip
  - `deployment/medallion/Dockerfile.dockerignore` — contexto limitado a `src/`
  - `deployment/medallion/compose.yaml` — servicio `medallion` one-shot con aislamiento
    completo (ver Diff/Arquitectura); build args `${MEDALLION_GIT_SHA:?}`/`${MEDALLION_IMAGE_TAG:?}`
  - `deployment/medallion/README.md` — build/run/despliegue + invariantes
  - `docs/phases/23/m8-medallion-deploy.md` — doc de milestone
  - `docs/phases/23/evidence/m8-*.log` — **16 evidencias** (preflight, deploy-copy×3 con
    2 fallos registrados, build×3 con 2 fallos registrados, UAT CLIs×3 con 2 fallos
    registrados —incluido un falso PASS por stdin truncado—, UAT replay, postcheck,
    GastosIA health, calidad repo×2, mark-done)
  - `docs/phases/23/commit-candidate-010.md` — este reporte
- **Modificados (2):** `docs/phases/23/evidence/log.md` (índice de evidencias),
  `harness/state/progress.yaml` (`23/m8-deploy` → `done` vía `progress.py mark-done`)
- **Eliminados:** ninguno

## Diff

```bash
$ git diff --cached --shortstat   # excluye este reporte (commit-candidate-010.md)
 23 files changed, 1162 insertions(+), 2 deletions(-)
$ git diff --cached --shortstat   # incluyendo este reporte
 24 files changed, 1333 insertions(+), 2 deletions(-)
$ git diff --cached --check
33 hallazgos trailing-whitespace — TODOS en evidencia cruda verbatim
  (docs/phases/23/evidence/m8-{03,05,06,06a,06b,07}-*.log, salida de progreso
  "Container … Creating " de docker compose); 0 hallazgos en deployment/,
  .md ni .yaml. pre-commit excluye ^docs/ (`exclude: ^(docs|harness|…)/`),
  por lo que ningún hook de calidad lo marca.
```

## Arquitectura afectada

- **Repo:** añade superficie de despliegue (`deployment/medallion/`) sin tocar código
  Python (0 ficheros bajo `src/`, `tests/`, `migrations/`, `config/`).
- **lenovosrv (fuera de git):** creado `/srv/docker/medallion/` (espejo de build,
  175 ficheros, paridad SHA-256 local/remoto verificada dos veces) + imagen
  `seta-medallion:m8-79b1de5b8fc8` = `sha256:df82686b…`; artefacto
  `/srv/fast/medallion/replay-work/m8/{ledger.jsonl,run2/ledger.jsonl}` (NVMe,
  reproducible/desechable). Canónico `/srv/data/medallion` **READ-ONLY** durante todo M8
  (manifest antes/después idéntico `154bf7f5…`).
- **Sin** daemon, scheduler, contenedor nuevo permanente, red, puerto, dependencia Python,
  servicio nuevo ni migración de plataforma (postgres/prometheus/grafana/GastosIA/paper
  con ID/StartedAt idénticos).

## Índice del grafo

- [x] Índice re-indexado al inicio de la sesión (`index_repository`, 20 838 nodos /
      47 534 aristas) tras detectarse desactualizado
- [ ] Re-indexar tras el commit autorizado (`index_repository`) — pendiente post-commit
- [ ] `check_index_coverage` sobre los archivos tocados — pendiente post-commit
      (`docs/`, `harness/state` excluidos por diseño; `deployment/medallion/*` es
      YAML/Dockerfile, sin nodos de grafo)

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| `ruff check .` + `ruff format --check .` + `mypy src tests` + `pytest tests --ignore=tests/integration` | PASS — **1184 passed, 1 skipped** (82 s) | `m8-09b-repo-quality-count.log` (variante con `-q` extra silenciaba el conteo → `m8-09-repo-quality.log`) |
| Preflight lenovosrv (SHA/rama/marker+UUID/LENOVO_DATA/NVMe/`SSD_MIN_FREE_GB`/baselines/canónico) | PASS | `m8-03-preflight.log` |
| Deploy copy (espejo + paridad SHA-256 + `compose config`) | PASS (2 fallos previos registrados) | `m8-04-deploy-copy.log` |
| Build + ligadura de SHA (`LABEL`/`/app/GIT_SHA`) | PASS (2 fallos previos registrados) | `m8-05c-build-verify.log` |
| UAT3: aislamiento + 5 CLIs en contenedor (sin writes) | PASS (2 fallos previos registrados) | `m8-06-uat-clis.log` |
| UAT4: replay M7 en contenedor ×3 (created/idéntico/skipped) | PASS — `LEDGER_PARITY=PASS`, rc=0 | `m8-07-uat-replay.log` |
| Postcheck (canónico/paper/PG/GastosIA/puertos/WF) | PASS | `m8-08-postcheck.log`, `m8-08b-gastosia-health.log` |
| Ledger del progreso | PASS — `registrado: 23/m8-deploy` (fase 23 → 11/13) | `m8-10-ledger-mark-done.log` |

## Cobertura

- Sin cambios en código Python ⇒ la cobertura del gate no se ve afectada por este commit
  (capa medallion medida en M7: **94.01%** con `--cov-fail-under=90`).
- Re-ejecución de la suite completa: **1184 passed, 1 skipped** (idéntica a M7).
- Scripts del arnés: sin cambios.

## Calidad

```bash
uv run ruff check .                 # All checks passed!
uv run ruff format --check .        # 326 files already formatted
uv run mypy src tests               # Success: no issues found in 285 source files
uv run pytest tests --ignore=tests/integration
                                    # 1184 passed, 1 skipped
```

## Seguridad

- [x] Sin secretos en el diff (grep -Ei `password|api_key|secret|token|BEGIN … PRIVATE`
  sobre `git diff --cached`: **15 líneas**, todas documentales/marcadores de verificación —
  textos "sin secretos", `NO_SECRETS_IN_CONFIG=OK` y el stderr `sudo: a password is required`
  del intento fallido registrado; **0 credenciales reales**, 0 hits en código fuente)
- [x] Contraseña sudo de la sesión: **0 ocurrencias** en el diff staged
      (`grep -c` sobre el valor de la contraseña sudo, no reproducido en el repo → 0). Las 4
      ocurrencias existentes en el repo son de
      evidencia preexistente de la fase 16 (deuda ya registrada). En M8 los scripts
      referencian `$SUDO_PASS` como variable (patrón M2) y el env no se registra en logs.
- [x] Sin `.env` ni credenciales en la imagen ni en el compose; env del contenedor limpio
      (verificado: `NO_SECRETS_IN_CONFIG=OK`, `CONTAINER_ENV_CLEAN=OK`)
- [x] Sin puertos publicados (`NEW_PORTS_PUBLISHED=0`), sin red de plataforma
- [x] Preexistente y NO de este commit: credencial sudo histórica ya versionada en
  evidencia de fase 16 → rotación/limpieza de historial en gate separado
  (`SECURITY_CREDENTIAL_ROTATION_REQUIRED=YES`, `GIT_HISTORY_CLEANUP_REQUIRED=YES`)

## Riesgos

- Bajo: solo ficheros de despliegue/docs; ningún código Python tocado (suite completa en verde).
- La imagen queda ligada al SHA por build arg + label + `/app/GIT_SHA`, pero `docker images`
  no permite verificar el SHA del trabajo local contra un registry (no hay push; digest local
  `sha256:df82686b…` registrado como evidencia).
- `read_only` + `cap_drop ALL` podrían complicar futuros CLIs que necesiten `/tmp` persistente
  o red (Bronze sí necesita red): M8 solo ejecuta replay aislado; Bronze/Silver/Gold en
  contenedor quedan fuera de alcance hasta M9+ con proposal propia.
- El compose exige `MEDALLION_GIT_SHA`/`MEDALLION_IMAGE_TAG` definidas (`:?`): cualquier
  build sin ellas falla de forma ruidosa (intencionado, fail-closed).

## Deuda técnica

- Re-indexar el grafo y verificar cobertura tras el commit (regla crítica §4.13).
- Falta un `deploy.sh`/Makefile que automatice espejo+build+run (hoy scripts manuales en
  `/tmp/opencode`, no versionados); candidato a M9 si se repite.
- El pull de `python:3.12-slim` vive en el content store de BuildKit (no aparece en
  `docker images`); un `docker builder prune` requeriría re-pull (aprobado).
- No hay healthcheck/daemon (correcto para one-shot): si en M9+ se quiere un scheduler,
  requerirá proposal de infraestructura propia.

## Mensaje de commit propuesto

```
feat(medallion): M8 one-shot container deploy on lenovosrv

- deployment/medallion: Dockerfile (python:3.12-slim, ARG GIT_SHA fail-closed
  40-hex + LABEL revision + /app/GIT_SHA, COPY src, sin pip, USER 1000:1000,
  CMD replay --help), Dockerfile.dockerignore (contexto = src/), compose.yaml
  one-shot (network_mode none, read_only + tmpfs, cap_drop ALL,
  no-new-privileges, mounts canonico ro / NVMe rw / marker ro, sin ports,
  sin platform-net, sin credenciales, build args obligatorios) y README
- UAT en lenovosrv: imagen seta-medallion:m8-79b1de5b8fc8 =
  sha256:df82686b... ligada al SHA; 5 CLIs verificados en contenedor sin
  writes; replay scripted M7 en contenedor -> ledger byte-identico a M7
  (sha 6d64b62b..., 1880793 trades, 23 cerrados), rc=0, RUN2 identico,
  RUN3 skipped; canonico (manifest 154bf7f5...), paper-runner y certificacion
  intactos; 0 puertos nuevos; WALK_FORWARD_READS=0 FINAL_HOLDOUT_READS=0
- ledger: 23/m8-deploy -> done; 16 evidencias m8-* (intentos fallidos
  registrados) + doc m8-medallion-deploy.md
```

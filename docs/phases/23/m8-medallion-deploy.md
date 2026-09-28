# M8 — Deploy Medallion en lenovosrv (batch/one-shot)

**Fecha:** 2026-09-28 (UTC-6)
**Rama:** `medalion` @ `79b1de5b8fc827397e608b698d315498b36ca92d` (precondición verificada: HEAD == SHA esperado, rama correcta, sin tracked files modificados)
**Alcance:** desplegar el runtime Medallion en lenovosrv bajo `/srv/docker/medallion/`,
con imagen ligada al SHA y ejecución del **mismo escenario scripted de M7** dentro de un
contenedor aislado, escribiendo el ledger de M8 en `/srv/fast/medallion/replay-work/m8/`.
**Destino:** `DEPLOY_PATH=/srv/docker/medallion` (data-root Docker, `710 root:root` ⇒
operaciones de fichero vía `sudo -S`, patrón M2).
**Gate:** instrucción directa del usuario (M8) + decisiones explícitas en sesión
(pull de base `python:3.12-slim` APPROVED; 3er mount `ro` del marker APPROVED).
Restricciones: NO commit, NO push, NO M9, NO bulk, NO service migration, NO tocar la
certificación paper, DETENERSE tras SALIDA.

## Qué se desplegó

### Repo (nuevos, 4 archivos)

| Archivo | Rol |
|---|---|
| `deployment/medallion/Dockerfile` | `FROM python:3.12-slim` + `ARG GIT_SHA` **fail-closed** (regex `^[0-9a-f]{40}$`: sin/inválido ⇒ build aborta) · `LABEL org.opencontainers.image.revision` · `ENV MEDALLION_GIT_SHA` · `/app/GIT_SHA` (0444) · `COPY src` (solo código) · **sin pip/secretos** (los 5 CLIs son stdlib puro) · `USER 1000:1000` · CMD one-shot `replay_cli --help` |
| `deployment/medallion/Dockerfile.dockerignore` | contexto de build limitado a `src/` (175 ficheros, 1,2 MB) |
| `deployment/medallion/compose.yaml` | servicio `medallion` one-shot: `network_mode: none` · `read_only` + `tmpfs /tmp` · `cap_drop: [ALL]` · `no-new-privileges` · `user 1000:1000` · 3 mounts · comando = replay M7 · **sin `ports`, sin `platform-net`, sin env de secretos, sin `restart`** · build args `GIT_SHA`/tag obligatorios (`${VAR:?}`) |
| `deployment/medallion/README.md` | build/run/despliegue + invariantes (docker-standards: documentar operación) |

### lenovosrv (espejo bit a bit del repo)

```text
/srv/docker/medallion/
├── .dockerignore
├── src/                                  (175 ficheros, MANIFEST sha local == remoto)
└── deployment/medallion/{Dockerfile,Dockerfile.dockerignore,compose.yaml,README.md}
```

La paridad se verificó con manifiesto SHA-256 idéntico local/remoto en el build
(`m8-04`) **y** de nuevo tras el UAT (`m8-08`: `DEPLOY_CTX_PARITY_FINAL=YES`).
El compose desplegado es literalmente el del repo (`context: ../..` resuelve a la raíz
del espejo igual que en el repo).

### Imagen

| Campo | Valor |
|---|---|
| `IMAGE_TAG` | `seta-medallion:m8-79b1de5b8fc8` (+ alias `seta-medallion:79b1de5b8fc827397e608b698d315498b36ca92d`) |
| `IMAGE_DIGEST` / ID | `sha256:df82686bfd6d87bacf9fdb2e01767b5c94c6d6040655fe93097ea9f065b73001` (`RepoDigests=seta-medallion@sha256:df82686b…`) |
| `LABEL revision` | `79b1de5b8fc827397e608b698d315498b36ca92d` |
| `/app/GIT_SHA` | `79b1de5b8fc827397e608b698d315498b36ca92d` (leído dentro de la imagen) |
| Base | `docker.io/library/python:3.12-slim` (Python 3.12.14) · 43,4 MB · build 5 s |
| `USER` | `1000:1000` (=`administrador`) |

## Aislamiento (verificado, no solo declarado)

| Control | Evidencia |
|---|---|
| `network_mode: none` | `m8-06` config + runtime: `/proc/net/dev` ⇒ **solo `lo`** |
| Sin `platform-net` | `m8-06` `NO_PLATFORM_NET=OK` |
| Sin puertos publicados | `m8-06` config sin `ports` + `m8-08` diff exacto contra baseline = `NEW_PORTS_PUBLISHED=0` |
| Sin credenciales / PG | `m8-06` config sin `password|secret|token|api_key|postgres`; env del contenedor limpio (solo PATH/LANG/PYTHON*/GIT_SHA/counters) |
| Canónico read-only | mounts `:ro` en config + runtime `EROFS` al escribir en `/srv/data/medallion` (`CANONICAL_WRITE_BLOCKED=OK`) |
| Marker ro + `--require-marker` | 3er mount `:ro` del marker (aprobado en sesión) ⇒ mismo check FAIL-CLOSED que M7 |
| Rootfs read-only | runtime `EROFS` en `/m8-probe` |
| `cap_drop: ALL` + `no-new-privileges` | config `m8-06` |
| No daemon | sin `restart`, sin scheduler, sin healthcheck; `docker compose run --rm` ⇒ contenedor borrado al terminar |

## Ejecución (evidencia en `docs/phases/23/evidence/`)

| Paso | Artefacto | Resultado |
|---|---|---|
| 03 preflight | `m8-03-preflight.log` | **PASS** — HEAD==SHA, worktree limpio; marker `LENOVO_DATA`+UUID `10fff707…` == fstab/blkid; `/srv/data`=sda1 ext4; `/srv/fast` en NVMe (395 GB libres ≥ `SSD_MIN_FREE_GB=50`); baseline paper-runner/PG/prometheus/grafana/GastosIA + puertos; canónico 36 ficheros, manifest `154bf7f5…`; M7 ledger `6d64b62b…`; sin contenedores/imagen Medallion |
| 04 deploy copy | `m8-04a-deploy-copy-fail.log` (sin `SUDO_PASS`) · `m8-04b-deploy-copy-fail.log` (traversal `710 root:root`) · `m8-04-deploy-copy.log` | **PASS** — espejo en `/srv/docker/medallion` vía `sudo -S`; **paridad SHA-256 local/remoto = `08d3227c…` (175 ficheros)**; `docker compose config --quiet` OK con todos los flags de aislamiento |
| 05 build | `m8-05-build.log` (exit 141 por `docker history\|head` con pipefail) · `m8-05b-build-verify-fail.log` (asserCIÓN `docker images\|grep python` inválida: el base vive en el content store de BuildKit) · `m8-05c-build-verify.log` | **PASS** — imagen `sha256:df82686b…`, `LABEL revision`==SHA, `/app/GIT_SHA`==SHA, `SHA_BINDING=PASS`, Python 3.12.14, base `python:3.12-slim` (pull único aprobado) |
| 06 UAT3 CLIs | `m8-06a-uat-clis-fail.log` (sonda `PermissionError` vs `EROFS`) · `m8-06b-uat-clis-incomplete.log` (**falso PASS**: `docker compose run` se comió el stdin del script remoto) · `m8-06-uat-clis.log` | **PASS** — aislamiento config+runtime OK; **5 CLIs disponibles** (`cli`, `silver_cli`, `candles_cli`, `gold_cli`, `replay_cli` + `IMPORTS_OK`); uid/gid 1000; env limpio; `NO_RESIDUAL_CONTAINERS`; sentinela `M8_REMOTE_SENTINEL_COMPLETE=YES` en todos los scripts remotos posteriores |
| 07 UAT4 replay | `m8-07-uat-replay.log` | **PASS** — RUN1 `STATUS=created` rc=0 (13 s) → `/srv/fast/medallion/replay-work/m8/ledger.jsonl`; **byte-idéntico a M7 (`cmp` + SHA)**; RUN2 (dir separado `m8/run2/`) byte-idéntico ⇒ determinismo; RUN3 `STATUS=skipped` ⇒ idempotencia; 24 líneas/23 registros; motivos `stop_loss:16 take_profit:2 trailing_stop:5`; 0 `.part`; sin contenedores ni redes residuales |
| 08 postcheck | `m8-08-postcheck.log` · `m8-08b-gastosia-health.log` | **PASS** — canónico manifest antes/después `154bf7f5…` idéntico ⇒ `CANONICAL_DATA_CHANGED=NO`; Bronze 5/Silver 28/Gold 3 intactos (Gold `9411a4e0…`/`be8aae2d…`); paper-runner ID/Image/StartedAt idénticos ⇒ `PAPER_CONTAINER_CHANGED=NO`; PG `healthy` (mismo id/started); prometheus/grafana/caddy running; GastosIA app HTTP **200** + samba `healthy`; `NEW_PORTS_PUBLISHED=0`; `CERTIFICATION_STATE_UNCHANGED=YES`; `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0` |
| 09 calidad repo | `m8-09-repo-quality.log` · `m8-09b-repo-quality-count.log` | **PASS** — ruff `All checks passed!` + 326 ficheros formateados + mypy `no issues in 285 files` + **1184 passed, 1 skipped** (el `-q` extra silenciaba el conteo: repetido sin `-q`) |

## Resultados UAT (lenovosrv)

- **DATASET_ID** = `gold-replay-a8c49e0be9154194841a97c4f26225a76cef9fba8d9a6d080198359c124ebdc3` (DEVELOPMENT 2024-06-01/02/03)
- **M7_LEDGER_HASH** = **M8_LEDGER_HASH** = `6d64b62b48575bdbcda19eb0dbbc46d53a7351606eb5fd93a9c038643a83e625` ⇒ **`LEDGER_PARITY=PASS`**
- Stats idénticas a M7: `total=45, filled=23, dropped=22, unfilled=0, closed=23, trades=1880793`
- RUN1 `created` (13 s, rc=0) → RUN2 byte-idéntico → RUN3 `skipped` (0 cambios)
- `CONTAINER_MODE=ONE_SHOT`: sin contenedores Medallion al terminar (`docker ps -a` = 0), sin redes `medallion`

## Decisiones tomadas en sesión (aprobadas por el usuario)

1. **`sudo -S` con `$SUDO_PASS`** para crear/ficherear bajo `/srv/docker` (`710 root:root`, patrón M2); la contraseña solo vivió en la sesión, jamás en ficheros ni evidencias.
2. **Pull de `python:3.12-slim`** (base ya declarada en el `Dockerfile` raíz) — gate de dependencia APPROVED.
3. **3er mount `ro` del marker** para conservar `--require-marker` (FAIL-CLOSED idéntico a M7), añadido a los 2 mounts exigidos por el spec.
4. **Lecciones registradas:** los scripts remotos por stdin exigen `</dev/null` en todo lo que lea stdin (`docker compose run`) + sentinela de completitud, para no aceptar PASS truncados.

## Condiciones de la regla M8 (post-ejecución)

1. Imagen ligada al SHA (`LABEL` + `/app/GIT_SHA` + build arg fail-closed) — PASS (`m8-05c`)
2. Aislamiento replay: `network_mode none` + canónico `ro` + sin creds/PG/platform-net/puertos — PASS (`m8-06`, `m8-08`)
3. CLIs bronze/silver/candles/gold/replay disponibles en el contenedor, **sin writes** de Bronze/Silver/Gold — PASS (`m8-06`)
4. Mismo escenario scripted de M7 sobre el mismo dataset, salida en `replay-work/m8/` — PASS (`m8-07`)
5. Ledger byte-idéntico / SHA idéntico a M7, 1 880 793 trades, 23 cerrados, determinista e idempotente, rc=0 — PASS (`m8-07`)
6. Sin contenedor Medallion corriendo al final — PASS (`m8-07`, `m8-08`)
7. `CANONICAL_DATA_CHANGED=NO`; hashes Bronze/Silver/Gold intactos — PASS (`m8-08`)
8. paper-runner ID/ImageID/StartedAt intactos; certificación intacta — PASS (`m8-08`)
9. GastosIA + PostgreSQL healthy; ningún puerto nuevo — PASS (`m8-08`, `m8-08b`)
10. `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0` — PASS (`m8-07`, `m8-08`)
11. Evidencia `m8-*` + doc creadas; calidad de repo verde — PASS (`m8-09*`)

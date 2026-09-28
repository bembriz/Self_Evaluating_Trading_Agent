# M0-II — GastosIA Backup + Restore Test

> **Fase:** 23 — Medallion Market Data & Trade-Level Replay
> **Entregable:** `m0ii-gastosia-rescue`
> **Fecha:** 2026-09-27/28 (UTC-6 / UTC)
> **Rama/HEAD:** `medalion` @ `df907c5d12fce6c0aee90adac5ae88e164633b5a` (verificado = `origin/medalion`, worktree limpio al inicio)
> **Autorización:** gate M0-II del usuario (COMMIT NO incluido; NO commit/push en esta fase)

---

## 1. Objetivo y alcance

Respaldar GastosIA **antes de formatear el HDD** y demostrar restauración completa en un entorno aislado.

Fuentes respaldadas (todas verificadas por SHA-256):

| Fuente | Bytes | Nota |
|---|---:|---|
| `/mnt/warehouse/GastosIA/` | 597.764 | **datos activos** — protocolo hash→copy→hash dedicado |
| `/mnt/warehouse/Hyper-V/VirtualMachines/GastosIA/` | 21.885.878.272 | legado VM (inerte en Ubuntu) |
| `/mnt/warehouse/PostgreSQL/` | 237.550.396 | legado data dir |
| `/home/administrador/gastos-ia-repo-backup-20260903.tar.gz` | 437.809 | repo legacy |
| `/srv/docker/gastos-ia/` (árbol completo: compose.yaml, `.env`, `cred/`, `repo/`) | 1.686.528 (tar) | leído via contenedor root `caddy:2-alpine` (sin sudo) |
| `pg_dump -Fc gastos_ia` | 73.316 | formato custom v1.15, PG 16.15 |
| `docker save gastos-ia-app:latest` | 229.633.024 | ID `sha256:b624dd56…` |
| metadata Docker redactada | 50 líneas | inspect+networks+images; **env SOLO claves** |
| env completo de la app | 1.264 | **secreto, chmod 600, NO impreso en evidencia** |

**Destino:** `/srv/backup-before-medallion/gastosia` (creado `gastosia.partial` → renombrado solo tras verificar; nunca sobrescribe backup existente).

## 2. Restricciones — cumplimiento

| Restricción | Estado |
|---|---|
| NO formatear/particionar/desmontar `/mnt/warehouse` | CUMPLIDO (solo lecturas + `cp -a`) |
| NO modificar `/etc/fstab` | CUMPLIDO (intocado) |
| NO detener/reiniciar GastosIA/PG/paper-runner | CUMPLIDO (ningún restart; IDs/StartedAt idénticos post) |
| NO modificar producción | CUMPLIDO (backup por lectura; PG solo SELECT + `pg_dump`) |
| NO tocar `~/.config/opencode/AGENTS.md` | CUMPLIDO |
| NO commit/push | CUMPLIDO (solo trabajo local) |
| Abortar si requiere quiesce de datos activos | NO REQUERIDO (consistente al intento 1) |
| No imprimir secretos | CUMPLIDO (env solo claves; password vía `$(… printenv …)` nunca en evidencia) |
| Puerto 80/443/445/139 y APIs Google/Gemini/Kimi | NO USADOS (app temporal sin puertos publicados en red `--internal` sin salida) |

## 3. Precheck

- Branch `medalion`, HEAD = `origin/medalion` = `df907c5…` ✓ (evidencia `m0ii-01`)
- Host `lenovosrv`; HDD por-id `ata-ST1000LM035-1RK172_WDEV3QGR` presente (montado `/dev/sda1 ntfs3`) ✓
- `/mnt/warehouse/GastosIA` legible (owner `administrador`) ✓
- NVMe libre pre-backup: **416,69 GiB**; destino inexistente (`DEST_FREE`) ✓ (`m0ii-02`)
- Baseline de contenedores corregido en `m0ii-02b` (template `.State.StartedAt`)
- `sudo -n` NO disponible → toda operación root sobre `/srv` y `/srv/docker` vía contenedores Docker con bind-mount (patrón `caddy:2-alpine`), sin instalar nada (infra-control: 0 instalaciones, 0 pulls — solo imágenes ya presentes)

## 4. Datos activos (protocolo exigido)

`hash origen → copiar → re-hash origen → comparar origen y destino` sobre `/mnt/warehouse/GastosIA` (`m0ii-06`):

- **Intento 1: CONSISTENT** (20 archivos, 597.764 B; árbol e hashes idénticos origen-pre/post/destino)
- `ACTIVE_DATA_ATTEMPTS=1`, `ACTIVE_DATA_QUIESCE_REQUIRED=NO` → no hubo que abortar

## 5. Validación del backup

1. `manifest.json` (generado localmente, sin secretos, scp al destino) + `SHA256SUMS` sobre **todos** los archivos salvo el propio checksum (`m0ii-10`, `m0ii-11`)
2. `sha256sum -c SHA256SUMS`: **5.234/5.234 OK, 0 FAILED, `VERIFY_RC=0`**
3. Rename `gastosia.partial → gastosia` solo tras exit=0 (target no existía)
4. Tamaño final: **22.356.469.017 B = 20,82 GiB**; NVMe libre post-backup: **425.064.939.520 B = 395,87 GiB** (margen sobre mínimo 50 GiB: **+345,87**)

## 6. Restore test aislado

Recursos temporales creados: red `m0ii-restore-net` (**`Internal=true`** — sin salida a internet ni a producción), PG `m0ii-restore-pg` (alias `postgres`, misma pass temporal tomada del env de prod **sin imprimirla**), volumen `m0ii-restore-vol`, app `m0ii-restore-app`, dir `/home/administrador/m0ii-restore-tmp`.

**Base de datos** (`m0ii-12`): `pg_isready` OK → `docker cp` del dump → `pg_restore --exit-on-error` **`RESTORE_RC=0`** → **10/10 tablas**, conteos idénticos:

```
alembic_version=1 audit_events=0 catalog_cache=64 expense_records=636
extraction_runs=10 image_files=15 processing_queue=10 sheet_sync=0
system_settings=0 users=2
```

`TABLE_COUNTS_MATCH=YES` · `ROW_COUNTS_MATCH=YES` · `DATABASE_RESTORE=PASS`

**Archivos** (`m0ii-13c`, corrección de `m0ii-13`/`m0ii-13b`):

- Extracción de `host/warehouse-GastosIA` + dump: 21 archivos → **21/21 SHA OK**
- Re-hash origen vivo vs restaurado: `RESTORED_EQ_ORIGIN=YES`
- Recibo legible: JPEG `ffd8ffe0`, `file` → `JPEG image data … 339x1280, components 3` → `RECEIPT_IMAGE_LEGIBLE=YES`
- **Cross-check extra:** los 15 `sha256_hash` de la tabla `image_files` (restaurada) coinciden con los archivos extraídos: **15/15** (`m0ii-14`)
- `FILE_RESTORE=PASS`

**Aplicación** (`m0ii-15a…15e`): `docker load` del tar del backup (imagen OK) → app temporal con env del backup, montajes mapeados a copias temporales (`/data/gastos` ← restaurado, `/app/cred` ← árbol extraído, RO), red interna, **0 puertos publicados**:

- `running=true restarts=0` · alembic aplicó contra la BD restaurada (`Context impl PostgresqlImpl`) · `Application startup complete` · uvicorn `:8000` → **HTTP 200** · TCP `postgres:5432` desde el contenedor OK
- **`APPLICATION_RESTORE_TEST=PASS`** (veredicto `m0ii-15e`)

**Artefactos de medición corregidos con transparencia** (logs crudos intactos, correcciones en corridas nuevas):

- `m0ii-13` exit=1: grep asumía líneas empezando por `./` (SHA256SUMS empieza por hash) → `m0ii-13b` con `grep -F` correcto (a su vez exit=1 por elegir `.crt` como "imagen" y `char(61)` ≠ `chr()` en SQL) → `m0ii-13c` exit=0
- `m0ii-15b/c/d` LIMITED: el conteo de `pg_stat_activity` es puntual (pool ocioso) y la imagen PG tiene `log_connections=off` (0 líneas `connection authorized`, y el prefijo por defecto no incluye `%h`) → medición imposible por esos canales; `m0ii-15e` usa la señal correcta (traza de alembic de la propia app = conexión viva requerida) → PASS

## 7. Limpieza y postcheck (`m0ii-16`, `m0ii-17`)

- Eliminados SOLO los temporales: contenedores `m0ii-restore-app/pg` (0 restos), volumen, red, dir tmp → `TEMP_RESOURCES_CLEANED=YES`
- Postcheck: **paper-runner** `id=b061332c…` / `image=sha256:e417…` / `started=2026-09-19T04:00:04.763010163Z` **idénticos al baseline** → `PAPER_CONTAINER_CHANGED=NO`
- GastosIA (app/caddy/samba) y PostgreSQL productivos: `running=true`, mismos IDs/StartedAt, `restarts=0` → `PRODUCTION_GASTOSIA_RUNNING=YES`, `PRODUCTION_POSTGRES_RUNNING=YES`
- **Backup re-verificado post-todo:** `REVERIFY_RC=0`, **5.234 OK / 0 FAILED** → intacto
- NVMe libre final: **395,87 GiB ≥ 50** ✓; sin restos temporales
- Certificación intacta: no se tocaron paper-runner ni cert (seguiría su ciclo normal)

## 8. Salida requerida

```
MEDALLION_M0II=PASS
BACKUP_CREATED=YES
ACTUAL_BACKUP_SIZE_GIB=20.82
NVME_FREE_AFTER_BACKUP_GIB=395.87
GASTOSIA_BACKUP_HASH_VERIFIED=YES
ACTIVE_DATA_CONSISTENT=YES
ACTIVE_DATA_QUIESCE_REQUIRED=NO
PG_DUMP_CREATED=YES
DATABASE_RESTORE=PASS
TABLE_COUNTS_MATCH=YES
ROW_COUNTS_MATCH=YES
FILE_RESTORE=PASS
APPLICATION_RESTORE_TEST=PASS
TEMP_RESOURCES_CLEANED=YES
PRODUCTION_GASTOSIA_RUNNING=YES
PRODUCTION_POSTGRES_RUNNING=YES
PAPER_CONTAINER_CHANGED=NO
CERTIFICATION_TOUCHED=NO
M0II_DELIVERABLE_STATE=DONE
M1_BLOCKED_BY_GLOBAL_RULE=YES
COMMIT_CANDIDATE_READY=YES
READY_FOR_M1_PREPARATION=YES   (preparar sí; ejecutar formateo NO — gobernanza global pendiente)
```

## 9. Evidencia (24 logs, `docs/phases/23/evidence/`)

| Log | exit | Contenido |
|---|---:|---|
| `m0ii-01-precheck-local` | 0 | branch/HEAD/origin/dirty |
| `m0ii-02-precheck-remote` | 0 | host/HDD/mount/NVMe/contenedores/destino (baseline con template erróneo, corregido abajo) |
| `m0ii-02b-baseline-sizing` | 0 | baseline corregido + tamaños origen + env keys |
| `m0ii-03-db-discovery` | 0 | env DB (sin pass) + imágenes + healthchecks |
| `m0ii-04-pg-superuser` | 0 | `POSTGRES_USER=trading`, 10 tablas, conn `gastos_app` |
| `m0ii-05-dest-skeleton` | 0 | esqueleto destino vía root container, chown 1000 |
| `m0ii-06-active-data` | 0 | protocolo datos activos: attempt 1 CONSISTENT |
| `m0ii-07-bulk-copy` | 0 | Hyper-V (3m14s) + PostgreSQL + repo tar, sizes iguales |
| `m0ii-08-docker-artifacts` | 0 | tar árbol, env 600 (no impreso), metadata, docker save |
| `m0ii-09-pg-dump` | 0 | pre-counts + dump custom 73.316 B + PG 16.15 |
| `m0ii-10-manifest-scp` | 0 | manifest.json al destino |
| `m0ii-11-sha-verify-rename` | 0 | SHA256SUMS 5.234 → `sha256sum -c` OK → rename final |
| `m0ii-12-restore-pg` | 0 | red interna + PG temporal + pg_restore + conteos |
| `m0ii-13-restore-files` | **1** | artefacto grep `./` (corregido en 13b) |
| `m0ii-13b-restore-files` | **1** | hash OK pero `.crt` elegido + SQL `char(61)` (corregido en 13c) |
| `m0ii-13c-restore-files` | 0 | 21/21 SHA + origen=destino + JPEG legible + schema |
| `m0ii-14-db-hash-crosscheck` | 0 | 15/15 hashes DB == archivos |
| `m0ii-15a-app-prep` | 0 | montajes + árbol compose extraído + red interna |
| `m0ii-15b-app-restore-test` | 0 | load + run + alembic/uvicorn (LIMITED por sonda puntual) |
| `m0ii-15c-app-db-proof` | 0 | HTTP 200; log-based imposible (`log_connections=off`) |
| `m0ii-15d-app-db-proof2` | 0 | TCP 5432 OK; ventana temporal sin datos (0 líneas) |
| `m0ii-15e-app-verdict` | 0 | **veredicto PASS** determinista |
| `m0ii-16-cleanup` | 0 | temporales eliminados, prod up |
| `m0ii-17-postcheck` | 0 | baseline == post; re-hash 5.234 OK; 395,87 GiB |

Índice máquina: `docs/phases/23/evidence/log.md` (24 entradas `m0ii-*`).

## 10. Notas / deuda

- El backup contiene **secretos reales** (`docker/gastos-ia-app.env` modo 600 + `cred/` dentro del tar): es un backup operativo-legítimo, pero si se copia fuera de lenovosrv debe cifrarse (pendiente de decisión en M1).
- `manifest.json` no incluye el tamaño total final (se calcula al sellar); el campo queda documentado aquí y en evidencia.
- Fallos preexistentes del arnés (2 tests `test_gen_pdf.py` por dependencias de reporte, coverage harness 33%) **no relacionados** con esta fase — sin cambios locales de código, no se re-ejecutaron suites.
- `M1` (formateo/medallion en HDD) sigue **bloqueado** por `GLOBAL_STORAGE_GOVERNANCE_CONFLICT_PENDING` (regla global en `~/.config/opencode/AGENTS.md:49`); el backup de este M0-II es el prerrequisito de seguridad que ese gate exigirá.

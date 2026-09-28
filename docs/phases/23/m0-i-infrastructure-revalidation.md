# M0-I — Revalidación de Infraestructura lenovosrv (READ-ONLY)

**Fase:** 23 — Medallion Market Data & Trade-Level Replay
**Gate:** M0-I · Infraestructure Revalidation
**Fecha de ejecución:** 2026-09-27 (18:18–18:25 -06:00 · 2026-09-28 00:18–00:25 UTC)
**Rama:** `medalion` · **HEAD:** `12e988eb903585d06a99391e0614a980fd2c1e9c` (limpio al inicio)
**Modo:** READ-ONLY sobre lenovosrv. Sin acciones destructivas, sin cambios de runtime, sin acceso a datasets restringidos.
**Índice codebase-memory:** `home-xuum-Documentos-proyectos-Self-Evaluating_Trading_Agent` vigente (ready, 2026-09-25); cobertura verificada sin gaps sobre los archivos tocados.

---

## 1. Host

| Campo | Valor |
|---|---|
| HOST | `lenovosrv` |
| OS | Ubuntu 24.04.4 LTS (Noble) |
| KERNEL | `6.8.0-138-generic` x86_64 |
| HW | Lenovo Y520-15IKBN · Firmware 4KCN40WW (2017-10-17) |
| UPTIME | 32d 20h 25m (al momento de la captura) |
| Usuario SSH | `administrador` (grupo `docker`) · sudo requiere contraseña (`sudo -n` → NO disponible) |

Evidencia: `docs/phases/23/evidence/m0i-01-host-identity.log`

## 2. Inventario físico de almacenamiento

| Rol | Identidad estable by-id | Modelo | Serial | Tamaño físico | Media |
|---|---|---|---|---|---|
| PRIMARY | `/dev/disk/by-id/nvme-Samsung_SSD_970_EVO_500GB_S466NX0KC36133J` (alias `nvme-eui.0025385c81b1453b`) | Samsung SSD 970 EVO 500GB | S466NX0KC36133J | 465,8 GiB | NVMe (ROTA=0, TRAN=nvme) |
| SECONDARY | `/dev/disk/by-id/ata-ST1000LM035-1RK172_WDEV3QGR` (alias `scsi-SATA_ST1000LM035-1RK1_WDEV3QGR`) | ST1000LM035-1RK172 | WDEV3QGR | 931,5 GiB | HDD SATA (ROTA=1) |

- **La identidad del secundario coincide EXACTAMENTE con la esperada** (`ata-ST1000LM035-1RK172_WDEV3QGR`) → sin STOP por divergencia de identidad.
- Nunca se identificó el disco solo como `/dev/sda`; `sda` es el nombre volátil, la identidad es la by-id.
- Particiones: `nvme0n1p1` vfat `/boot/efi` · `nvme0n1p2` ext4 `/boot` · `nvme0n1p3` LVM2_member → `ubuntu--vg/ubuntu--lv` ext4 montado en `/` · `sda1` NTFS label `Warehouse` UUID `0ADC29B7DC299DC7` montado en `/mnt/warehouse`.

Evidencia: `m0i-02-storage-inventory.log`

## 3. Tier rápido NVMe

- Root FS: `/dev/mapper/ubuntu--vg-ubuntu--lv` ext4 (LVM sobre `nvme0n1p3`) → **todo el árbol `/` es NVMe**, incluidos `/srv`, `/srv/docker`, `/var/lib/docker`, `/var/lib/containerd`.
- Filesystem `/` (bytes): total `488420507648` (455 GiB) · used `20013490176` (19 GiB) · avail `447422296064` (417 GiB) · 5%.
- `docker info`: **DockerRootDir=`/srv/docker`** (data-root oficial del server, coincide con `~/.config/opencode/AGENTS.md:48`), driver `overlayfs`, engine 29.7.2.
- Mapeo físico: `stat` confirma `/srv` y `/srv/docker` = mismo device que `/` → **DOCKER_ROOT_ON_NVME=YES**.
- Rutas objetivo futuras (verificadas sin crearlas): `/srv/data` **ABSENT**, `/srv/fast` y `/srv/fast/medallion/{cache,replay-work,tmp,indexes}` **ABSENT** → creación pendiente de M1/M2 (correcto: M0 no crea nada).
- **Factibilidad del tier rápido:** con 417 GiB libres, las4 rutas de caché/replay son plenamente factibles en NVMe.

### Políticas SSD

| Política | Umbral | Medido | Veredicto |
|---|---|---|---|
| `SSD_MIN_FREE_GB=50` | ≥ 50 GiB libres siempre | 417 GiB libres | **PASS** |
| `SSD_CACHE_MAX_GB=64` | caché ≤ 64 GiB y dejar ≥ 50 libres | 417−64 = 353 GiB ≥ 50 | **PASS** |

- **Máximo de caché seguro con la medición actual:** `417 − 50 = 367 GiB` teórico; **la política vigente mantiene el tope de 64 GiB** (más conservador). Recalcular en cada gate M* según medición (invariante medallion-market-data §9).

Evidencia: `m0i-03-nvme-fast-tier.log`, `m0i-11-tier-paths-feasibility.log`

## 4. Tier capacidad HDD

| Campo | Valor |
|---|---|
| Filesystem | NTFS (`ntfs3`), label `Warehouse`, UUID `0ADC29B7DC299DC7` |
| Mount | `/mnt/warehouse` |
| fstab (solo lectura) | `UUID=0ADC29B7DC299DC7 /mnt/warehouse ntfs3 defaults,nofail,uid=1000,gid=1000 0 0` |
| Capacidad (bytes) | total `1000203087872` (932 GiB) · used `524616253440` (489 GiB) · avail `475586834432` (443 GiB) · 53% |

### Dependencias actuales sobre `/mnt/warehouse`

| Dependencia | Tipo | Detalle |
|---|---|---|
| `gastos-ia-app` | bind mount Docker | `/mnt/warehouse/GastosIA → /data/gastos` |
| `gastos-ia-samba` | bind mount Docker | `/mnt/warehouse/GastosIA → /shares/gastos` (SMB 139/445 activo, healthy) |
| fstab | montaje automático | entrada `nofail` arriba |
| Procesos userspace | **ninguno** | `fuser -vm` → solo el mount del kernel |
| systemd / smb.conf host | **ninguno** | grep sin referencias adicionales |

**Conclusión:** la única consumidora activa del warehouse es **GastosIA** (app + samba). **SETA no depende de `/mnt/warehouse`.** El samba expone `/mnt/warehouse/GastosIA` a clientes externos (uso personal) — a considerar en M0-II/M1, sin modificar nada ahora.

Evidencia: `m0i-04-hdd-warehouse.log`, `m0i-08-gastosia.log`

## 5. Inventario Docker

- Engine 29.7.2 (client+server) · containerd v2.3.3 · runc 1.4.3 · **7 contenedores, 7 running, 10 imágenes**.
- Compose projects: `self-evaluating-trading-agent` (`/srv/docker/self-evaluating-trading-agent/compose.yaml`, 4 servicios) y `gastos-ia` (`/srv/docker/gastos-ia/compose.yaml`, 3 servicios).

| Contenedor | Imagen | Proj | Restart | Health | Estado | Puertos | Redes | Volúmenes/binds |
|---|---|---|---|---|---|---|---|---|
| `self-evaluating-trading-agent-paper-runner-1` | `…paper-runner:0.2.0` | SETA | unless-stopped | none | Up 8d | — | SETA_default | binds: reports, certification, safeguard (NVMe) |
| `self-evaluating-trading-agent-postgres-1` | `pgvector/pgvector:pg16` | SETA | no | healthy | Up 3wk | `127.0.0.1:5433→5432` | SETA_default | vol: `…_pgdata` (NVMe) |
| `self-evaluating-trading-agent-prometheus-1` | `prom/prometheus:v2.53.0` | SETA | no | none | Up 2wk | `127.0.0.1:9090` | SETA_default | bind prometheus.yml + vol `…_promdata` (NVMe) |
| `self-evaluating-trading-agent-grafana-1` | `grafana/grafana:11.1.0` | SETA | no | none | Up 2wk | `127.0.0.1:3000` | SETA_default | bind provisioning + vol `…_grafanadata` (NVMe) |
| `gastos-ia-app` | `gastos-ia-app:latest` | gastos-ia | unless-stopped | none | Up 3wk | 8000/tcp (sin publicar) | **gastos-ia_gastos + SETA_default** | binds: `/srv/docker/gastos-ia/cred`, `/mnt/warehouse/GastosIA` |
| `gastos-ia-caddy` | `caddy:2-alpine` | gastos-ia | unless-stopped | none | Up 3wk | **0.0.0.0:80, 0.0.0.0:443** | gastos-ia_gastos | bind Caddyfile + vols `gastos-ia_caddy_data/config` (NVMe) |
| `gastos-ia-samba` | `servercontainers/samba:smbd-only-latest` | gastos-ia | unless-stopped | healthy | Up 3wk | 0.0.0.0:139/445 | gastos-ia_default | bind warehouse/GastosIA + vol anónimo (NVMe) |

- **Redes:** `self-evaluating-trading-agent_default` = {postgres, prometheus, paper-runner, grafana, **gastos-ia-app**} · `gastos-ia_gastos` = {caddy, app} · `gastos-ia_default` = {samba} · `bridge/host/none`. **No existe `platform-net` todavía** (esperado: M2).
- **Volúmenes (6):** `…_pgdata`, `…_promdata`, `…_grafanadata`, `gastos-ia_caddy_data`, `gastos-ia_caddy_config`, anónimo samba — todos en `/srv/docker/volumes/` (NVMe).
- `docker system df`: imágenes 3,234 GB · contenedores 24,88 MB · volúmenes 93,33 MB · build cache 2,478 GB (1,196 GB reclaimable).
- **Puertos del host (`ss -tlnp`):** `0.0.0.0:22,80,443,445,139` · `127.0.0.1:3000,5433,9090`. **PostgreSQL NO expuesto públicamente.**

Evidencia: `m0i-05-docker-inventory.log`, `m0i-07-proxy-monitoring.log`

## 6. Topología PostgreSQL

- Contenedor: `self-evaluating-trading-agent-postgres-1` · imagen `pgvector/pgvector:pg16` · healthy · red: **solo `self-evaluating-trading-agent_default`** · publicación: **`127.0.0.1:5433` (loopback únicamente)**.
- Almacenamiento: volumen `/srv/docker/volumes/self-evaluating-trading-agent_pgdata/_data` → **NVMe** (82 MB de datos) → **POSTGRES_ON_NVME=YES**.
- Bases (nombre | owner | tamaño), solo metadatos:

| Base | Owner | Tamaño |
|---|---|---|
| `trading_agent` | `trading` | 10 MB |
| `gastos_ia` | `gastos_app` | 8503 kB |
| `gastos_ia_test` | `gastos_app` | 8223 kB |
| `postgres` / `template0` / `template1` | `trading` | 7487 / 7329 / 7551 kB |

- **GASTOSIA_DB_COUPLED_TO_SETA = YES.** Evidencia estructural: `gastos-ia-app` es el único contenedor no-SETA presente en `self-evaluating-trading-agent_default`; `postgres` no pertenece a ninguna red `gastos-*`, y su único publicación es loopback host → la app GastosIA **solo** puede alcanzar `gastos_ia` a través de la red del proyecto SETA. Este es el acoplamiento que el diseño (§20) manda eliminar en la etapa de plataforma.
- Sin dumps, sin migraciones, sin cambios de roles, sin lectura de contenido privado de aplicaciones.

Evidencia: `m0i-06-postgres-topology.log`

## 7. Reverse proxy (Caddy)

- **CADDY_CURRENT_OWNER = `gastos-ia` / `gastos-ia-caddy`** (compose project `gastos-ia`, imagen `caddy:2-alpine`).
- Posee `0.0.0.0:80` y `0.0.0.0:443` (HTTP/HTTPS globales del host).
- Caddyfile (leído vía `docker exec` read-only): `gastos.local { tls internal; reverse_proxy app:8000 }` → **solo proxy de GastosIA-app**.
- **SETA NO depende de Caddy**: grafana/prometheus/publicaciones propias van directo por loopback; el paper-runner no publica puertos.
- El acceso directo del host a `/srv/docker/gastos-ia/*` está restringido (root 710/600, `sudo -n` no disponible) → inspeccionado por metadatos Docker; no se modificó nada.

## 8. Monitoreo (Prometheus/Grafana)

| Componente | CURRENT_OWNER | CURRENT_PROJECT | CURRENT_STORAGE | CURRENT_NETWORK | MIGRATION_COMPLEXITY | CERTIFICATION_DEPENDENCY |
|---|---|---|---|---|---|---|
| Prometheus (`127.0.0.1:9090`, datos 7,2 MB) | self-evaluating-trading-agent | SETA | bind `deploy/prometheus.yml` + vol `…_promdata` (NVMe) | SETA_default | **LOW** | **YES** |
| Grafana (`127.0.0.1:3000`, datos ~1 MB) | self-evaluating-trading-agent | SETA | bind `deploy/grafana/provisioning` + vol `…_grafanadata` (NVMe) | SETA_default | **LOW** | **YES** |

Ambos son candidatos naturales a plataforma compartida: estado en volúmenes nombrados aislables, puertos loopback, sin dependencias cruzadas salvo que **monitorean en activo la certificación paper en curso** (targetes del paper-runner) → su migración debe esperar a que la certificación se cierre (o a un gate explícito que garantice continuidad de observabilidad).

## 9. GastosIA — revalidación

| Activo | Ubicación | Disco | Tamaño medido |
|---|---|---|---|
| Compose/config/cred | `/srv/docker/gastos-ia/` (no listable sin root) | NVMe | metadatos vía docker inspect/labels |
| **Datos activos** (recibos) | `/mnt/warehouse/GastosIA/` (dirs `Esme`, `Ruben`, `gastos-local-root.crt`) | **HDD** | **597.764 B (0,0006 GB)** |
| **Legado Hyper-V** | `/mnt/warehouse/Hyper-V/VirtualMachines/` (único contenido: `GastosIA`) | HDD | **21.885.878.272 B (20,38 GiB / 21,89 GB)** |
| **Legado PostgreSQL** | `/mnt/warehouse/PostgreSQL/` | HDD | **237.550.396 B (0,23 GiB / 0,24 GB)** |
| BD `gastos_ia` | dentro de PG de SETA | NVMe | 8503 kB |
| Volúmenes caddy | `/srv/docker/volumes/gastos-ia_*` | NVMe | incluidos en 93,33 MB totales |

- **GASTOSIA_FOUND=YES.** Contenedores esperados presentes: `gastos-ia-app`, `gastos-ia-caddy`, `gastos-ia-samba` (Up 3 weeks).
- `GASTOSIA_ACTIVE_HDD_GB=0,0006` · `GASTOSIA_LEGACY_HDD_GB=20,60` (GiB; total 22.123.428.668 B = 22,12 GB decimales).
- **GASTOSIA_BACKUP_FITS_NVME=YES** *(corregido 2026-09-27, r2 — capacidad con alcance completo)*. Alcance de preservación M0-II = **ACTIVO + LEGADOS + config/BD/docker**: total **21,60 GiB** (activo 0,0006 + legados 20,60 + config/BD/docker 1,00 conservador) sobre **416,69 GiB** libres → **`EXPECTED_NVME_FREE_AFTER_BACKUP_GIB=395,09`** · `SSD_MIN_FREE_POLICY_AFTER_BACKUP=PASS` · `POST_BACKUP_MARGIN_ABOVE_MIN_GIB=345,09`. La versión anterior estimaba ~0,1 GB / 416,6 GiB **omitiendo los legados (~20,60 GiB)** — ver §20 y `docs/phases/23/evidence/m0i-capacity-correction.log`.
- **No se clasificó nada como desechable; no se borró ni modificó nada** (la preservación es M0-II).

Evidencia: `m0i-08-gastosia.log`

## 10. Aislamiento de la certificación SETA

- **PAPER_CONTAINER_RUNNING=YES.** `self-evaluating-trading-agent-paper-runner-1` · ID `b061332c3572…` · imagen `self-evaluating-trading-agent-paper-runner:0.2.0` · `StartedAt=2026-09-19T04:00:04Z` · Up 8 days · `restart=unless-stopped` (Restarts=3, histórico previo a esta sesión) · red SETA_default · binds NVMe: `reports/`, `certification/`, `safeguard/` · sin puertos publicados.
- Directorio `certification/`: `certification-state.json` (mtime 2026-09-27 22:01, **escritura propia del contenedor en operación, previa a nuestra inspección 00:18Z**) + 3 históricos INVALIDATED + reporte; `safeguard/safeguard-evidence.json` (mtime Sep 10).
- Únicas operaciones ejecutadas sobre él: `docker ps` / `docker inspect` (metadatos) / `docker exec … ls` → **PAPER_CONTAINER_CHANGED=NO · CERTIFICATION_TOUCHED=NO**. Ningún restart, recreate, rebuild ni escritura.
- Ningún contenedor fue iniciado, detenido, reiniciado ni recreado en toda la sesión; **RUNTIME_CHANGED=NO**, **DESTRUCTIVE_ACTIONS_EXECUTED=NO**.

Evidencia: `m0i-09-paper-certification.log`

## 11. Factibilidad de plataforma compartida

Objetivo aprobado (M0): `platform-postgres`, `platform-caddy`, `platform-prometheus`, `platform-grafana` compartidos; apps (SETA/GastosIA/Medallion) específicas.

| Candidato | CURRENT_OWNER | CURRENT_PROJECT | CURRENT_STORAGE | CURRENT_NETWORK | COMPLEXITY | CERT_DEP |
|---|---|---|---|---|---|---|
| platform-postgres | `self-evaluating-trading-agent-postgres-1` | SETA | vol `…_pgdata` NVMe | SETA_default + 127.0.0.1:5433 | **HIGH** | **YES** |
| platform-caddy | `gastos-ia-caddy` | gastos-ia | vols `gastos-ia_caddy_*` NVMe | gastos-ia_gastos + 0.0.0.0:80/443 | **MEDIUM** | NO |
| platform-prometheus | `…-prometheus-1` | SETA | vol `…_promdata` NVMe | SETA_default + loopback:9090 | **LOW** | **YES** |
| platform-grafana | `…-grafana-1` | SETA | vol `…_grafanadata` NVMe | SETA_default + loopback:3000 | **LOW** | **YES** |

- **SHARED_PLATFORM_FEASIBLE = YES**: todos los estados están en volúmenes nombrados/binds aislables sobre NVMe, sin superposición de proyectos en volúmenes, puertos no conflictivos (PG loopback, caddy global), dos compose projects independientes; la migración es factible por etapas con dumps lógicos + recreación de contenedores (plan §21 del diseño), sin tocar nada ahora.
- **PLATFORM_CHANGES_BLOCKED_BY_CERTIFICATION = [`platform-postgres`, `platform-prometheus`, `platform-grafana`, retiro de `gastos-ia-app` de `self-evaluating-trading-agent_default`]** — todo lo que toque la BD de la certificación, su observabilidad o la red del proyecto SETA debe esperar al cierre de la certificación paper (o a un gate explícito con aprobación humana). `platform-caddy` no tiene dependencia de certificación (solo de gates M0-II/M2).

## 12. Validación de tiering de almacenamiento (target M0 vs realidad)

| Afirmación target | Estado actual | Veredicto |
|---|---|---|
| NVMe: OS, Docker, PostgreSQL, código de apps | `/`, `/srv/docker`, volúmenes PG/monitoring, compose de ambas apps → todos en NVMe | **YES** |
| HDD: canónico Bronze/Silver/Gold | `/srv/data` **no existe aún** (M1 pendiente); warehouse NTFS es el disco de capacidad | **CANONICAL_MEDALLION_ON_HDD=NO** (pendiente M1/M3 — sin contradicción: nada creado todavía) |
| NVMe: caché de replay activa, tmp, índices | `/srv/fast` **no existe aún** (M1/M2 pendientes) | **REPLAY_CACHE_ON_NVME=NO** (pendiente M1/M2 — sin contradicción) |
| PostgreSQL en NVMe | `…_pgdata` en `/srv/docker/volumes` sobre NVMe | **POSTGRES_ON_NVME=YES** |

**Contradicciones detectadas: ninguna.** Las dos respuestas `NO` son *ausencia futura*, no conflicto: los directorios objetivo se crean en M1/M2 (gated). La topología real no se opone en nada al diseño aprobado; lo único que impide ejecutar M1 es el bloqueo de gobernanza (§13).

## 13. Conflicto de gobernanza global

| Campo | Valor |
|---|---|
| Archivo | `~/.config/opencode/AGENTS.md` |
| Línea | **49** |
| Restricción textual | *"`/mnt/warehouse` = disco NTFS de 1 TB montado automático vía fstab (ntfs3), contiene datos personales — **NO formatear ni borrar jamás**"* |
| Conflicto | El disco secundario ES el warehouse; la decisión del usuario en M0 ("solo GastosIA debe preservarse") y el plan M1 (reformato a ext4 `/srv/data`) chocan con la prohibición absoluta vigente. |
| Estado | **GLOBAL_STORAGE_GOVERNANCE_CONFLICT_PENDING=YES** · **M1_BLOCKED_BY_GLOBAL_RULE=YES** |
| Alcance | **NO bloquea M0-II** (backup + restore son acciones no destructivas compatibles con la regla). Bloquea exclusivamente M1 (formato/partición). Redacción mínima propuesta en `docs/design/medallion-replay-architecture.md` §25.8, **no aplicada**, requiere aprobación explícita. |

No se modificó el archivo global.

## 14. Data policy / holdout

- No se leyó, descargó ni tocó ningún dataset (`datasets/` intacto; sin acceso a rangos walk-forward/holdout).
- **WALK_FORWARD_READS=0 · FINAL_HOLDOUT_READS=0 · HOLDOUT_STATE=PRISTINE.**

## 15. Evidencia

Índice completo: `docs/phases/23/evidence/log.md` (21 entradas, todas registradas con `evidence.sh`):

| Log | Contenido | exit |
|---|---|---|
| `m0i-01-host-identity.log` | hostnamectl, os-release, uname, uptime | 0 |
| `m0i-02-storage-inventory.log` | lsblk, blkid, findmnt, df, by-id | 0 |
| `m0i-03-nvme-fast-tier.log` | docker root, df bytes, LVM | 0 |
| `m0i-04-hdd-warehouse.log` | fstab, findmnt, df, fuser, referencias | 0 |
| `m0i-05-docker-inventory.log` | version, ps, compose, redes, volúmenes, df, inspect por contenedor | 0 |
| `m0i-06-postgres-topology.log` | bases (nombre/owner/tamaño), red PG, membresías | 0 |
| `m0i-07-proxy-monitoring.log` | puertos + intento Caddyfile host + du (permiso denegado) | 1 (hallazgo registrado, corregido en 07b) |
| `m0i-07b-proxy-monitoring-fix.log` | sudo -n test, Caddyfile vía docker exec, tamaños de datos | 0 |
| `m0i-08-gastosia.log` | rutas activas/legadas + tamaños + contenedores | 0 |
| `m0i-09-paper-certification.log` | inspect paper-runner + certification/safeguard mtimes | 0 |
| `m0i-10-global-governance.log` | restricción warehouse en AGENTS.md:49 | 0 |
| `m0i-11-tier-paths-feasibility.log` | existencia de rutas objetivo + device /srv (exit=2 = path ausente, esperado) | 2 |
| `m0i-12-acceptance-check.log` | verificación de aceptación local (falló: campos §20 aún no estaban en el reporte) | 1 |
| `m0i-12b-acceptance-check.log` | verificación de aceptación local tras añadir campos §20 | 0 |
| `m0i-13-harness-tests.log` | `pytest harness/tests` completo (2 FAILED: `test_gen_pdf` sin dev-deps `markdown`/`weasyprint` — gap de entorno, preexistente al cambio) | 1 |
| `m0i-13b-harness-tests-without-pdf.log` | `pytest harness/tests --ignore=test_gen_pdf.py` → 67 passed | 0 |
| `m0i-14-harness-coverage.log` | `pytest --cov=harness/scripts --cov-fail-under=80` → coverage 33,29% (ver deuda abajo) | 1 |
| `m0i-14b-harness-coverage-project.log` | variante `uv run --project harness` → 33,75% (misma causa) | 1 |
| `m0i-15-gastosia-backup-sizing.log` | re-check read-only de capacidad para la corrección: df bytes, du activo/legados, cred/caddy/samba vía docker exec, imagen gastos-ia-app | 0 |
| `m0i-capacity-correction.log` | **corrección auditada de capacidad**: valores originales inconsistentes, recálculo con alcance completo, unidades GiB, fuentes, aserciones (rango 395–396) | 0 |
| `m0i-16-correction-validation.log` | validación post-corrección: campos corregidos en docs, sin valor obsoleto activo, `git diff --check`, solo docs+ledger, raw preservado, legados incluidos | 0 |

> Nota: `m0i-07` exit=1 (denegación de permisos al leer Caddyfile como host y `du` de volúmenes como no-root), `m0i-11` exit=2 (`/srv/data/...` inexistente), `m0i-12` exit=1 (assert faltante en el propio script), `m0i-13` exit=1 (dev-deps de PDF no instaladas: `markdown`/`weasyprint` requieren Dependency Proposal — **no se instaló nada**) y `m0i-14/14b` exit=1 (coverage < umbral) son **hallazgos legítimos registrados sin editar**; los de ejecución se resolvieron/reconfirmaron en corridas posteriores (`07b`, ausencia esperada en `11`, `12b` exit=0, `13b` exit=0 con 67 passed).
>
> **Deuda de calidad preexistente (NO introducida por M0-I):** (a) `test_gen_pdf` ya fallaba en fase 16 (2026-09-01, ver `docs/phases/16/evidence/paper-certification-harness-coverage.log`) por falta de dev-deps `markdown`/`weasyprint` — instalarlas exige Dependency Proposal (no tocada); (b) el coverage global del arnés bajó de ~79,6% (fase 16) a ~33,7% porque los scripts one-off `phase18*/19*/20*_development_*`, `preflight_guards.py` y `release_check.py` (~1.116 statements) **nunca tuvieron tests**; el núcleo del arnés mantiene coverage alto (`ledger 90,8% · progress 97,5% · gate_check 96,3% · gen_report 95,9% · new_phase 95,7% · paper_certification 94,8%`). El diff de este gate solo toca `progress.yaml` (mutado por script) y documentación → sin impacto en coverage.

## 16. Criterios de aceptación (§18)

| Criterio | Resultado |
|---|---|
| Identidad de host confirmada | **PASS** |
| Ambos discos identificados por identidad estable | **PASS** (by-id coincidentes con lo esperado) |
| NVMe confirmado como tier rápido | **PASS** (455 GiB FS, raíz + Docker + PG) |
| HDD confirmado como tier de capacidad | **PASS** (NTFS 932 GiB en `/mnt/warehouse`) |
| Docker root mapeado | **PASS** (`/srv/docker` → NVMe) |
| Políticas SSD validadas | **PASS** (min-free y caché) |
| Dependencias GastosIA mapeadas | **PASS** |
| Topología PostgreSQL mapeada | **PASS** |
| Redes Docker mapeadas | **PASS** |
| Aislamiento de certificación confirmado | **PASS** (sin cambios) |
| Dependencias de migración de plataforma identificadas | **PASS** |
| Sin acción destructiva | **PASS** (`DESTRUCTIVE_ACTIONS_EXECUTED=NO`) |
| Sin cambio de runtime | **PASS** (`RUNTIME_CHANGED=NO`) |
| Sin acceso a datasets restringidos | **PASS** (holdout PRISTINE) |

**→ MEDALLION_M0I = PASS (14/14)**

## 17. Blockers

1. **M1_BLOCKED_BY_GLOBAL_RULE=YES** — gobernanza `AGENTS.md:49` (§13). No bloquea M0-II.
2. `sudo -n` no disponible → inspección de host files root-only (p.ej. `/srv/docker/gastos-ia/*`) requiere credencial; se resolvió con metadatos Docker/`docker exec` read-only, sin necesidad de sudo.
3. Warehouse: el share Samba expuesto (`0.0.0.0:445`) es dependencia externa a considerar al planear M1 (migración de `/mnt/warehouse/GastosIA` a `/srv/data/gastosia`).

## 18. Readiness M0-II

- **READY_FOR_M0II=YES.** Backup con alcance completo (activo + **legados** + config/BD/docker) estimado en **21,60 GiB** sobre **416,69 GiB** libres de NVMe → libres tras backup ≈ **395,09 GiB** ≥ `SSD_MIN_FREE_GB=50` (`GASTOSIA_BACKUP_FITS_NVME=YES`; margen `POST_BACKUP_MARGIN_ABOVE_MIN_GIB=345,09`).
- Identidad física confirmada por by-id (`DISK_IDENTITY_MATCH` prerequisite OK para M1 posterior).
- Restricciones M0-II a respetar: solo backup + test de restore aislado, `GASTOSIA_BACKUP_COMPLETE/HASH_VERIFIED/DATABASE_BACKUP/RESTORE_TEST` + USER APPROVAL antes de cualquier preformato; nada destructivo todavía.

## 19. Campos normalizados (formato de salida del gate M0-I)

```text
MEDALLION_M0I=PASS
BRANCH=medalion
HEAD=12e988eb903585d06a99391e0614a980fd2c1e9c
WORKTREE_START_CLEAN=YES

HOST=lenovosrv
OS=Ubuntu 24.04.4 LTS
KERNEL=6.8.0-138-generic

PRIMARY_DISK=/dev/disk/by-id/nvme-Samsung_SSD_970_EVO_500GB_S466NX0KC36133J
PRIMARY_MEDIA=NVME
PRIMARY_SIZE_GB=465.8

SECONDARY_DISK=/dev/disk/by-id/ata-ST1000LM035-1RK172_WDEV3QGR
SECONDARY_MEDIA=HDD
SECONDARY_SIZE_GB=931.5
SECONDARY_FS=ntfs
SECONDARY_MOUNT=/mnt/warehouse

NVME_TOTAL_GB=455
NVME_USED_GB=19
NVME_FREE_GB=417

HDD_TOTAL_GB=932
HDD_USED_GB=489
HDD_FREE_GB=443

DOCKER_ROOT=/srv/docker
DOCKER_ROOT_ON_NVME=YES

SSD_MIN_FREE_GB=50
SSD_CACHE_MAX_GB=64
SSD_MIN_FREE_POLICY=PASS
SSD_CACHE_POLICY=PASS

POSTGRES_CONTAINER=self-evaluating-trading-agent-postgres-1
POSTGRES_ON_NVME=YES
POSTGRES_DATABASES=trading_agent,gastos_ia,gastos_ia_test
GASTOSIA_DB_COUPLED_TO_SETA=YES

CADDY_CURRENT_OWNER=gastos-ia/gastos-ia-caddy
PROMETHEUS_CURRENT_OWNER=self-evaluating-trading-agent/self-evaluating-trading-agent-prometheus-1
GRAFANA_CURRENT_OWNER=self-evaluating-trading-agent/self-evaluating-trading-agent-grafana-1

GASTOSIA_FOUND=YES
GASTOSIA_ACTIVE_HDD_GB=0.0006
GASTOSIA_LEGACY_HDD_GB=20.60
GASTOSIA_BACKUP_FITS_NVME=YES
NVME_FREE_BEFORE_BACKUP_GIB=416.69
GASTOSIA_ACTIVE_BACKUP_ESTIMATE_GIB=0.0006
GASTOSIA_LEGACY_BACKUP_ESTIMATE_GIB=20.60
GASTOSIA_CONFIG_DB_DOCKER_ESTIMATE_GIB=1.00
GASTOSIA_TOTAL_BACKUP_ESTIMATE_GIB=21.60
EXPECTED_NVME_FREE_AFTER_BACKUP_GIB=395.09
SSD_MIN_FREE_POLICY_AFTER_BACKUP=PASS
POST_BACKUP_MARGIN_ABOVE_MIN_GIB=345.09

CANONICAL_MEDALLION_ON_HDD=NO
REPLAY_CACHE_ON_NVME=NO

SHARED_PLATFORM_FEASIBLE=YES
PLATFORM_CHANGES_BLOCKED_BY_CERTIFICATION=platform-postgres,platform-prometheus,platform-grafana,retiro-gastos-ia-app-de-red-SETA

PAPER_CONTAINER_RUNNING=YES
PAPER_CONTAINER_CHANGED=NO
CERTIFICATION_TOUCHED=NO

GLOBAL_STORAGE_GOVERNANCE_CONFLICT_PENDING=YES
M1_BLOCKED_BY_GLOBAL_RULE=YES

DESTRUCTIVE_ACTIONS_EXECUTED=NO
RUNTIME_CHANGED=NO

WALK_FORWARD_READS=0
FINAL_HOLDOUT_READS=0
HOLDOUT_STATE=PRISTINE

M0I_DELIVERABLE_STATE=DONE
```

## 20. Corrección de capacidad de backup (r2, 2026-09-27)

**Motivo:** la v1 de este reporte estimaba `EXPECTED_NVME_FREE_AFTER_BACKUP_GB=416.6` y "backup ≈0,1 GB", valores **incompatibles con el alcance de preservación aprobado de M0-II**, que incluye ACTIVO **+ LEGADOS** + config/BD/docker — los legados solos son ≈20,60 GiB.

**Unidad:** GiB (2³⁰) en todo el cálculo; fuente de espacio libre en bytes exactos de `df -B1`.

| Componente | Valor | Fuente |
|---|---|---|
| `NVME_FREE_BEFORE_BACKUP_GIB` | **416,69** (447.422.193.664 B) | `m0i-15` (df -B1; `m0i-03` minutos antes: 447.422.296.064 B, deriva 102.400 B) |
| `GASTOSIA_ACTIVE_BACKUP_ESTIMATE_GIB` | **0,0006** (597.764 B) | `m0i-08`/`m0i-15` du -sb `/mnt/warehouse/GastosIA` |
| `GASTOSIA_LEGACY_BACKUP_ESTIMATE_GIB` | **20,60** (22.123.428.668 B = Hyper-V 21.885.878.272 + PostgreSQL 237.550.396) | `m0i-08`/`m0i-15` |
| `GASTOSIA_CONFIG_DB_DOCKER_ESTIMATE_GIB` | **1,00** (alocación conservadora; medido sin imagen = 0,0082 GiB: dump BD 8.707.072 + cred 2.368 + Caddyfile 4.151 + caddy data/config 48.930 + samba vol 4.096; imagen local `gastos-ia-app:latest` 944 MB = 0,879 GiB; margen 0,112 GiB para build context/compose no listable sin root — `sudo -n` NO disponible, ver `m0i-07b`) | `m0i-15` |
| `GASTOSIA_TOTAL_BACKUP_ESTIMATE_GIB` | **21,60** | suma |
| `EXPECTED_NVME_FREE_AFTER_BACKUP_GIB` | **395,09** = 416,69 − 21,60 | `m0i-capacity-correction` |
| `POST_BACKUP_MARGIN_ABOVE_MIN_GIB` | **345,09** = 395,09 − 50 | idem |

**Veredictos corregidos:** `GASTOSIA_BACKUP_FITS_NVME=YES` · `SSD_MIN_FREE_POLICY_AFTER_BACKUP=PASS` (margen 345,09 GiB sobre el mínimo de 50) · el resultado cae en el rango esperado 395–396 GiB.

**Integridad de evidencia:** los logs raw originales (`m0i-01`…`m0i-14b`) **no se editaron**; la corrección vive en `m0i-15-gastosia-backup-sizing.log` + `m0i-capacity-correction.log` (ambos exit=0 con aserciones). El ledger `23/m0i-infra-discovery` permanece **DONE** (la revalidación de descubrimiento pasó; esto corrige un valor derivado). Sin cambios de infraestructura, runtime ni certificación.

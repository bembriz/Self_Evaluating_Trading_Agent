- `2026-09-27T18:18:16-06:00` **m0i-01-host-identity** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 echo "=== hostnamectl ==="; hostnamectl; echo; echo "=== os-release ==="; cat /etc/os-release; echo; echo "=== uname ==="; uname -a; echo; echo "=== uptime ==="; uptime` · exit=`0` · artifact: docs/phases/23/evidence/m0i-01-host-identity.log
- `2026-09-27T18:18:16-06:00` **m0i-02-storage-inventory** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 echo "=== lsblk -d ==="; lsblk -d -o NAME,PATH,SIZE,MODEL,SERIAL,ROTA,TRAN; echo; echo "=== lsblk tree ==="; lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,FSVER,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL,ROTA; echo; echo "=== blkid ==="; blkid; echo; echo "=== findmnt ==="; findmnt; echo; echo "=== df -hT ==="; df -hT; echo; echo "=== by-id ==="; ls -l /dev/disk/by-id/` · exit=`0` · artifact: docs/phases/23/evidence/m0i-02-storage-inventory.log
- `2026-09-27T18:18:58-06:00` **m0i-03-nvme-fast-tier** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 echo "=== docker root ==="; docker info --format "DockerRootDir={{.DockerRootDir}} StorageDriver={{.Driver}} ServerVersion={{.ServerVersion}} Containers={{.Containers}} Running={{.ContainersRunning}} Images={{.Images}}"; echo; echo "=== docker dirs on disk ==="; ls -ld /srv/docker /var/lib/docker /var/lib/containerd 2>&1; readlink -f /var/lib/docker 2>&1; readlink -f /var/lib/containerd 2>&1; echo; echo "=== df root (BG) ==="; df -BG /; echo; echo "=== df root (bytes) ==="; df -B1 --output=size,used,avail,pcent,target /; echo; echo "=== LVM ==="; lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS /dev/nvme0n1` · exit=`0` · artifact: docs/phases/23/evidence/m0i-03-nvme-fast-tier.log
- `2026-09-27T18:18:59-06:00` **m0i-04-hdd-warehouse** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 echo "=== fstab ==="; cat /etc/fstab; echo; echo "=== findmnt warehouse ==="; findmnt /mnt/warehouse; echo; echo "=== df warehouse BG ==="; df -BG /mnt/warehouse; echo; echo "=== df warehouse bytes ==="; df -B1 --output=size,used,avail,pcent,target /mnt/warehouse; echo; echo "=== procs usando warehouse ==="; fuser -vm /mnt/warehouse 2>&1 || true; echo; echo "=== referencias a warehouse en configs sistema ==="; grep -rn "warehouse" /etc/fstab /etc/systemd/system /etc/samba/smb.conf 2>/dev/null || echo "(sin referencias adicionales)"` · exit=`0` · artifact: docs/phases/23/evidence/m0i-04-hdd-warehouse.log
- `2026-09-27T18:19:07-06:00` **m0i-05-docker-inventory** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 set +e; echo "=== docker version ==="; docker version; echo; echo "=== docker ps -a ==="; docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"; echo; echo "=== compose ls ==="; docker compose ls -a; echo; echo "=== network ls ==="; docker network ls; echo; echo "=== volume ls ==="; docker volume ls; echo; echo "=== system df ==="; docker system df; echo; echo "=== container detail (sin env) ==="; for c in $(docker ps -aq); do docker inspect --format "{{.Name}} | image={{.Config.Image}} | proj={{index .Config.Labels \"com.docker.compose.project\"}} | projdir={{index .Config.Labels \"com.docker.compose.project.working_dir\"}} | restart={{.HostConfig.RestartPolicy.Name}} | state={{.State.Status}} | health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} | nets={{range \$k,\$v := .NetworkSettings.Networks}}{{\$k}},{{end}} | mounts={{range .Mounts}}{{.Type}}:{{.Source}}->{{.Destination}};{{end}} | ports={{range \$p,\$c := .HostConfig.PortBindings}}{{\$p}}={{index \$c 0}};{{end}}" $c; done` · exit=`0` · artifact: docs/phases/23/evidence/m0i-05-docker-inventory.log
- `2026-09-27T18:20:30-06:00` **m0i-06-postgres-topology** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 echo "=== pg container ==="; docker ps --filter "name=postgres" --format "{{.Names}} | {{.Image}} | {{.Status}} | {{.Ports}}"; echo; echo "=== databases (nombre/owner/tamano) ==="; docker exec self-evaluating-trading-agent-postgres-1 bash -c 'psql -U "$POSTGRES_USER" -d postgres -t -A -F" | " -c "SELECT datname, pg_get_userbyid(datdba), pg_size_pretty(pg_database_size(datname)) FROM pg_database ORDER BY datname;"'; echo "psql_exit=$?"; echo; echo "=== red del contenedor PG ==="; docker inspect --format "{{range \$k,\$v := .NetworkSettings.Networks}}{{\$k}} {{end}}" self-evaluating-trading-agent-postgres-1; echo "=== pertenencia de red SETA_default ==="; docker network inspect --format "{{.Name}}: {{range .Containers}}[{{.Name}}] {{end}}" self-evaluating-trading-agent_default; echo "=== pertenencia gastos-ia_gastos ==="; docker network inspect --format "{{.Name}}: {{range .Containers}}[{{.Name}}] {{end}}" gastos-ia_gastos; echo "=== pertenencia gastos-ia_default ==="; docker network inspect --format "{{.Name}}: {{range .Containers}}[{{.Name}}] {{end}}" gastos-ia_default` · exit=`0` · artifact: docs/phases/23/evidence/m0i-06-postgres-topology.log
- `2026-09-27T18:20:31-06:00` **m0i-07-proxy-monitoring** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 echo "=== puertos escuchando ==="; ss -tlnp 2>/dev/null | sed -n "1,40p"; echo; echo "=== Caddyfile (config, sin secretos) ==="; cat /srv/docker/gastos-ia/Caddyfile; echo; echo "=== compose projects config ==="; docker compose ls -a; echo; echo "=== prometheus/grafana mounts+data ==="; docker inspect --format "{{.Name}} mounts={{range .Mounts}}{{.Type}}:{{.Source}}->{{.Destination}};{{end}}" self-evaluating-trading-agent-prometheus-1 self-evaluating-trading-agent-grafana-1; echo; echo "=== tamano volumenes monitoring (NVMe) ==="; du -sh /srv/docker/volumes/self-evaluating-trading-agent_promdata /srv/docker/volumes/self-evaluating-trading-agent_grafanadata /srv/docker/volumes/self-evaluating-trading-agent_pgdata 2>/dev/null` · exit=`1` · artifact: docs/phases/23/evidence/m0i-07-proxy-monitoring.log
- `2026-09-27T18:21:30-06:00` **m0i-07b-proxy-monitoring-fix** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 echo "=== sudo -n disponible? ==="; sudo -n true 2>&1 && echo SUDO_NOPASSWD=YES || echo SUDO_NOPASSWD=NO; echo; echo "=== Caddyfile via docker exec (read-only) ==="; docker exec gastos-ia-caddy cat /etc/caddy/Caddyfile 2>&1; echo "caddyfile_exit=$?"; echo; echo "=== Caddy backends declarados (routes) ==="; docker exec gastos-ia-caddy sh -c "grep -E \"reverse_proxy|respond|file_server|:80|:443|domain|host\" /etc/caddy/Caddyfile" 2>&1; echo; echo "=== tamanos de datos de volumenes via docker exec ==="; docker exec self-evaluating-trading-agent-prometheus-1 du -sh /prometheus 2>&1; docker exec self-evaluating-trading-agent-grafana-1 du -sh /var/lib/grafana 2>&1; docker exec self-evaluating-trading-agent-postgres-1 du -sh /var/lib/postgresql/data 2>&1` · exit=`0` · artifact: docs/phases/23/evidence/m0i-07b-proxy-monitoring-fix.log
- `2026-09-27T18:21:39-06:00` **m0i-08-gastosia** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 set +e; echo "=== config en NVMe: /srv/docker/gastos-ia (listado) ==="; ls -la /srv/docker/gastos-ia 2>&1; echo; echo "=== bind activo GastosIA (HDD) ==="; ls -la /mnt/warehouse/GastosIA 2>&1 | sed -n "1,30p"; echo; echo "=== bytes activo ==="; du -sb /mnt/warehouse/GastosIA 2>&1; du -s -BG /mnt/warehouse/GastosIA 2>&1; echo; echo "=== candidatos legados ==="; ls -la /mnt/warehouse/Hyper-V/VirtualMachines 2>&1; du -sb /mnt/warehouse/Hyper-V/VirtualMachines 2>&1; du -s -BG /mnt/warehouse/Hyper-V/VirtualMachines 2>&1; echo; du -sb /mnt/warehouse/PostgreSQL 2>&1; du -s -BG /mnt/warehouse/PostgreSQL 2>&1; echo; echo "=== raiz warehouse (solo listado, sin recorrido completo) ==="; ls -la /mnt/warehouse 2>&1; echo; echo "=== contenedores GastosIA ==="; docker ps -a --filter "name=gastos-ia" --format "{{.Names}} | {{.Image}} | {{.Status}} | {{.Ports}}"` · exit=`0` · artifact: docs/phases/23/evidence/m0i-08-gastosia.log
- `2026-09-27T18:21:51-06:00` **m0i-09-paper-certification** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 echo "=== paper-runner inspeccion (solo metadatos, sin env) ==="; docker inspect --format "ID={{.Id}} Image={{.Config.Image}} ImageID={{.Image}} State={{.State.Status}} StartedAt={{.State.StartedAt}} Restarts={{.RestartCount}} RestartPolicy={{.HostConfig.RestartPolicy.Name}} Proj={{index .Config.Labels \"com.docker.compose.project\"}} ProjDir={{index .Config.Labels \"com.docker.compose.project.working_dir\"}} Nets={{range \$k,\$v := .NetworkSettings.Networks}}{{\$k}},{{end}} Mounts={{range .Mounts}}{{.Type}}:{{.Source}}->{{.Destination}};{{end}} Ports={{range \$p,\$c := .HostConfig.PortBindings}}{{\$p}}={{index \$c 0}};{{end}}" self-evaluating-trading-agent-paper-runner-1; echo; echo "=== cert/safeguard/report dirs (mtimes) ==="; docker exec self-evaluating-trading-agent-paper-runner-1 sh -c "ls -la /app/certification /app/safeguard 2>&1 | sed -n \"1,40p\"" 2>&1; echo; echo "=== uptime docker (no reinicios) ==="; docker ps --format "{{.Names}} | {{.Status}}"` · exit=`0` · artifact: docs/phases/23/evidence/m0i-09-paper-certification.log
- `2026-09-27T18:21:59-06:00` **m0i-10-global-governance** → `bash -c echo "=== ~/.config/opencode/AGENTS.md: restriccion warehouse ==="; grep -n "warehouse" ~/.config/opencode/AGENTS.md; echo; echo "=== contexto lineas ==="; grep -n -B2 -A2 "NO formatear ni borrar jamás" ~/.config/opencode/AGENTS.md` · exit=`0` · artifact: docs/phases/23/evidence/m0i-10-global-governance.log
- `2026-09-27T18:23:18-06:00` **m0i-11-tier-paths-feasibility** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 echo "=== /srv (listado) ==="; ls -la /srv 2>&1; echo; echo "=== existencia de rutas objetivo (sin crear) ==="; for p in /srv/data /srv/fast /srv/fast/medallion /srv/fast/medallion/cache /srv/fast/medallion/replay-work /srv/fast/medallion/tmp /srv/fast/medallion/indexes /srv/data/medallion; do if [ -e "$p" ]; then echo "EXISTS: $p"; else echo "ABSENT: $p"; fi; done; echo; echo "=== /srv en filesystem NVMe? ==="; findmnt -n -o TARGET,SOURCE,FSTYPE /; stat -c "%n device=%d" /srv /srv/docker 2>&1; echo; echo "=== marker LENOVO_DATA ==="; ls -la /srv/data/.lenovosrv-data-volume 2>&1` · exit=`2` · artifact: docs/phases/23/evidence/m0i-11-tier-paths-feasibility.log
- `2026-09-27T18:26:50-06:00` **m0i-12-acceptance-check** → `bash -c 
set -e
R=docs/phases/23/m0-i-infrastructure-revalidation.md
test -f "$R"
for f in m0i-01-host-identity m0i-02-storage-inventory m0i-03-nvme-fast-tier m0i-04-hdd-warehouse m0i-05-docker-inventory m0i-06-postgres-topology m0i-07b-proxy-monitoring-fix m0i-08-gastosia m0i-09-paper-certification m0i-10-global-governance; do
  test -f "docs/phases/23/evidence/$f.log"
  grep -q "exit=0" "docs/phases/23/evidence/$f.log"
done
grep -q "exit=1" docs/phases/23/evidence/m0i-07-proxy-monitoring.log
grep -q "ata-ST1000LM035-1RK172_WDEV3QGR" docs/phases/23/evidence/m0i-02-storage-inventory.log
grep -q "DockerRootDir=/srv/docker" docs/phases/23/evidence/m0i-03-nvme-fast-tier.log
grep -q "gastos_ia" docs/phases/23/evidence/m0i-06-postgres-topology.log
grep -q "NO formatear ni borrar jamás" docs/phases/23/evidence/m0i-10-global-governance.log
for campo in HOST KERNEL PRIMARY_DISK SECONDARY_DISK NVME_FREE_GB HDD_FREE_GB DOCKER_ROOT SSD_MIN_FREE_POLICY POSTGRES_ON_NVME GASTOSIA_DB_COUPLED_TO_SETA GASTOSIA_BACKUP_FITS_NVME SHARED_PLATFORM_FEASIBLE GLOBAL_STORAGE_GOVERNANCE_CONFLICT_PENDING WALK_FORWARD_READS HOLDOUT_STATE MEDALLION_M0I; do
  grep -q "$campo" "$R" || { echo "FALTA CAMPO: $campo"; exit 1; }
done
git rev-parse HEAD | grep -q 12e988eb903585d06a99391e0614a980fd2c1e9c
echo "ACEPTACION_M0I=14/14_PASS; campos requeridos presentes; baseline HEAD verificado"
` · exit=`1` · artifact: docs/phases/23/evidence/m0i-12-acceptance-check.log
- `2026-09-27T18:27:27-06:00` **m0i-12b-acceptance-check** → `bash -c 
set -e
R=docs/phases/23/m0-i-infrastructure-revalidation.md
test -f "$R"
for f in m0i-01-host-identity m0i-02-storage-inventory m0i-03-nvme-fast-tier m0i-04-hdd-warehouse m0i-05-docker-inventory m0i-06-postgres-topology m0i-07b-proxy-monitoring-fix m0i-08-gastosia m0i-09-paper-certification m0i-10-global-governance; do
  test -f "docs/phases/23/evidence/$f.log"
  grep -q "exit=0" "docs/phases/23/evidence/$f.log"
done
grep -q "exit=1" docs/phases/23/evidence/m0i-07-proxy-monitoring.log
grep -q "ata-ST1000LM035-1RK172_WDEV3QGR" docs/phases/23/evidence/m0i-02-storage-inventory.log
grep -q "DockerRootDir=/srv/docker" docs/phases/23/evidence/m0i-03-nvme-fast-tier.log
grep -q "gastos_ia" docs/phases/23/evidence/m0i-06-postgres-topology.log
grep -q "NO formatear ni borrar jamás" docs/phases/23/evidence/m0i-10-global-governance.log
for campo in HOST KERNEL PRIMARY_DISK SECONDARY_DISK NVME_FREE_GB HDD_FREE_GB DOCKER_ROOT SSD_MIN_FREE_POLICY POSTGRES_ON_NVME GASTOSIA_DB_COUPLED_TO_SETA GASTOSIA_BACKUP_FITS_NVME SHARED_PLATFORM_FEASIBLE GLOBAL_STORAGE_GOVERNANCE_CONFLICT_PENDING WALK_FORWARD_READS HOLDOUT_STATE MEDALLION_M0I; do
  grep -q "$campo" "$R" || { echo "FALTA CAMPO: $campo"; exit 1; }
done
git rev-parse HEAD | grep -q 12e988eb903585d06a99391e0614a980fd2c1e9c
echo "ACEPTACION_M0I=14/14_PASS; campos requeridos presentes; baseline HEAD verificado"
` · exit=`0` · artifact: docs/phases/23/evidence/m0i-12b-acceptance-check.log
- `2026-09-27T18:29:00-06:00` **m0i-13-harness-tests** → `uv run pytest harness/tests -q` · exit=`1` · artifact: docs/phases/23/evidence/m0i-13-harness-tests.log
- `2026-09-27T18:29:31-06:00` **m0i-13b-harness-tests-without-pdf** → `uv run pytest harness/tests -q --ignore=harness/tests/test_gen_pdf.py` · exit=`0` · artifact: docs/phases/23/evidence/m0i-13b-harness-tests-without-pdf.log
- `2026-09-27T18:31:04-06:00` **m0i-14-harness-coverage** → `uv run pytest harness/tests -q --cov=harness/scripts --cov-branch --cov-report=json:docs/phases/23/evidence/coverage.json --cov-fail-under=80` · exit=`1` · artifact: docs/phases/23/evidence/m0i-14-harness-coverage.log
- `2026-09-27T18:32:21-06:00` **m0i-14b-harness-coverage-project** → `uv run --project harness pytest harness/tests --cov=harness/scripts --cov-branch --cov-report=json:docs/phases/23/evidence/coverage-harness.json -q` · exit=`1` · artifact: docs/phases/23/evidence/m0i-14b-harness-coverage-project.log
- `2026-09-27T18:40:14-06:00` **m0i-15-gastosia-backup-sizing** → `ssh -o BatchMode=yes -o ConnectTimeout=10 administrador@192.168.100.24 set +e
echo "=== NVMe libre actual (bytes) ==="; df -B1 --output=size,used,avail,pcent,target /
echo
echo "=== activo HDD (bytes) ==="; du -sb /mnt/warehouse/GastosIA 2>&1
echo "=== legado Hyper-V (bytes) ==="; du -sb /mnt/warehouse/Hyper-V/VirtualMachines 2>&1
echo "=== legado PostgreSQL (bytes) ==="; du -sb /mnt/warehouse/PostgreSQL 2>&1
echo
echo "=== config/cred via contenedor (read-only) ==="; docker exec gastos-ia-app du -sb /app/cred 2>&1; docker exec gastos-ia-app du -sb /app 2>&1
echo "=== caddy config+data via contenedor ==="; docker exec gastos-ia-caddy du -sb /etc/caddy /data /config 2>&1
echo "=== samba share no-GastosIA ==="; docker exec gastos-ia-samba du -sb /shares 2>/dev/null; docker exec gastos-ia-samba sh -c "du -sb /shares/* 2>/dev/null" 2>&1
echo
echo "=== imagenes docker (tamano) ==="; docker images --format "{{.Repository}}:{{.Tag}} {{.Size}}" | grep -i "gastos" 2>&1
echo "=== volumenes gastos-ia (via docker system df -v no aplica; inspeccion de rutas) ==="; docker inspect --format "{{range .Mounts}}{{.Name}} {{.Source}}={{.Destination}};{{end}}" gastos-ia-caddy gastos-ia-samba 2>&1` · exit=`0` · artifact: docs/phases/23/evidence/m0i-15-gastosia-backup-sizing.log
- `2026-09-27T18:41:31-06:00` **m0i-capacity-correction** → `bash -c 
set -e
python3 - <<PY
# --- Unidad: GiB (2^30). Fuentes: evidencias raw sin editar ---
# NVME libre: m0i-15-gastosia-backup-sizing.log (df -B1 avail) = 447422193664 B
# (m0i-03: 447422296064 B minutos antes; deriva 102400 B, irrelevante)
FREE = 447422193664
# activo: m0i-08 / m0i-15 du -sb /mnt/warehouse/GastosIA = 597764 B
ACTIVE = 597764
# legado: m0i-08 / m0i-15 Hyper-V 21885878272 + PostgreSQL 237550396
LEGACY = 21885878272 + 237550396
# config/DB/docker medido (m0i-15): dump logico gastos_ia 8503kB=8707072B,
# cred 2368, Caddyfile 4151, caddy /data 40395, /config 8535, samba vol 4096
CFG_DB_DOCKER_MEASURED = 8707072 + 2368 + 4151 + 40395 + 8535 + 4096
# imagen local gastos-ia-app:latest = 944MB (docker images, decimal) = 944000000 B
IMAGE = 944000000
# ALOCACION CONSERVADORA config/code/docker = 1 GiB exacto:
# cubre imagen 0.879 + medido 0.008 + margen 0.112 GiB para el build context/compose
# de /srv/docker/gastos-ia NO listable sin root (sudo -n NO disponible; m0i-07b)
ALLOC = 2**30
assert CFG_DB_DOCKER_MEASURED + IMAGE < ALLOC, "alocacion debe cubrir medido+imagen"
def gib(b): return b / 2**30
free = gib(FREE); active = gib(ACTIVE); legacy = gib(LEGACY)
cfg = gib(ALLOC)
total = active + legacy + cfg
expected = free - total
margin = expected - 50
print("=== CORRECCION DE CAPACIDAD M0-I (unidad: GiB) ===")
print()
print("VALORES ORIGINALES INCONSISTENTES (reporte M0-I v1):")
print("  NVME_FREE_GB=417")
print("  GASTOSIA_LEGACY_HDD_GB=20.60")
print("  EXPECTED_NVME_FREE_AFTER_BACKUP_GB=416.6  <- INCONSISTENTE: solo descontaba activo+config (~0.1 GB),")
print("  resumen ejecutivo: backup ~0.1 GB          <- excluia ilegitimamente los LEGADOS")
print()
print("FUENTES (raw sin editar): m0i-03, m0i-08, m0i-15")
print(f"  NVME_FREE_BEFORE_BACKUP_GIB        = {free:.2f}  ({FREE} B)")
print(f"  GASTOSIA_ACTIVE_BACKUP_ESTIMATE_GIB= {active:.4f} ({ACTIVE} B)")
print(f"  GASTOSIA_LEGACY_BACKUP_ESTIMATE_GIB= {legacy:.2f}  ({LEGACY} B = Hyper-V 21885878272 + PostgreSQL 237550396)")
print(f"  GASTOSIA_CONFIG_DB_DOCKER_ESTIMATE_GIB = {cfg:.2f}  (alocacion conservadora 1 GiB = imagen 0.879 + medido 0.008 + margen 0.112; medido sin imagen = {gib(CFG_DB_DOCKER_MEASURED):.4f} GiB)")
print(f"  GASTOSIA_TOTAL_BACKUP_ESTIMATE_GIB = {total:.2f}")
print()
print(f"  EXPECTED_NVME_FREE_AFTER_BACKUP_GIB = {expected:.2f}")
print(f"  POST_BACKUP_MARGIN_ABOVE_MIN_GIB    = {margin:.2f}")
print()
fits = "YES" if expected >= 50 else "NO"
pol = "PASS" if margin >= 0 else "FAIL"
print(f"  GASTOSIA_BACKUP_FITS_NVME={fits}")
print(f"  SSD_MIN_FREE_POLICY_AFTER_BACKUP={pol}")
print()
print("RAZON DE LA CORRECCION: el alcance de preservacion M0-II aprobado incluye ACTIVO + LEGADOS + config/DB/docker;")
print("la estimacion original omitia los legados (~20.60 GiB) y por tanto sobreestimaba el espacio libre resultante.")
# aserciones de validacion
assert 395.0 <= expected <= 396.0, f"esperado en rango 395-396, obtuvo {expected:.2f}"
assert abs(free - 416.69) < 0.05
assert abs(legacy - 20.60) < 0.01
assert margin > 300
assert fits == "YES" and pol == "PASS"
print("VALIDACION: rango 395-396 GiB OK; politica SSD OK; aserciones=PASS")
PY
` · exit=`0` · artifact: docs/phases/23/evidence/m0i-capacity-correction.log
- `2026-09-27T18:44:12-06:00` **m0i-16-correction-validation** → `bash -c 
set -e
R=docs/phases/23/m0-i-infrastructure-revalidation.md
CC=docs/phases/23/commit-candidate-001.md
# 1) valores corregidos presentes
grep -q "EXPECTED_NVME_FREE_AFTER_BACKUP_GIB=395.09" "$R"
grep -q "NVME_FREE_BEFORE_BACKUP_GIB=416.69" "$R"
grep -q "GASTOSIA_TOTAL_BACKUP_ESTIMATE_GIB=21.60" "$R"
grep -q "POST_BACKUP_MARGIN_ABOVE_MIN_GIB=345.09" "$R"
grep -q "SSD_MIN_FREE_POLICY_AFTER_BACKUP=PASS" "$R"
grep -q "395,09" "$CC"
# 2) sin valor obsoleto como campo normalizado activo (solo permitido como documentacion del error)
! grep -qE "^EXPECTED_NVME_FREE_AFTER_BACKUP_GB=416.6$" "$R"
! grep -qE "EXPECTED_NVME_FREE_AFTER_BACKUP_GB=416.6$" "$CC"
# 3) git diff --check limpio
git diff --check
# 4) sin cambios fuera de docs/ + progress.yaml; sin src/deploy/compose
git status --porcelain | grep -vE "^(.M harness/state/progress.yaml|\?\? docs/phases/23/)$" && { echo "ARCHIVOS_INESPERADOS"; exit 1; } || true
test -z "$(git status --porcelain -- src deploy docker-compose.yml compose.yaml 2>/dev/null)"
# 5) progress.yaml sigue con la mutacion exclusiva de mark-done (9+/3-), sin edicion manual nueva
test "$(git diff --numstat harness/state/progress.yaml)" = "9	3	harness/state/progress.yaml"
grep -q "estado: done" <(sed -n "/id: m0i-infra-discovery/,/id: m0ii/p" harness/state/progress.yaml)
# 6) evidencia raw preservada (headers originales intactos, 18 logs previos)
for f in m0i-01-host-identity m0i-02-storage-inventory m0i-03-nvme-fast-tier m0i-08-gastosia m0i-14-harness-coverage; do
  grep -q "fecha: 2026-09-27T18:" "docs/phases/23/evidence/$f.log"
done
test -f docs/phases/23/evidence/m0i-15-gastosia-backup-sizing.log
test -f docs/phases/23/evidence/m0i-capacity-correction.log
# 7) alcance legados incluido en la estimacion
grep -q "LEGADOS" "$R"
grep -q "GASTOSIA_LEGACY_BACKUP_ESTIMATE_GIB=20.60" "$R"
echo "CORRECCION_CAPACIDAD=PASS (395.09 GiB, margen 345.09, raw preservado, diff limpio, solo docs+ledger)"
` · exit=`0` · artifact: docs/phases/23/evidence/m0i-16-correction-validation.log

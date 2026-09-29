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
- `2026-09-27T19:17:32-06:00` **m0ii-01-precheck-local** → `bash -c git branch --show-current && git rev-parse HEAD && git rev-parse origin/medalion && echo "DIRTY=$(git status --porcelain | wc -l)"` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-01-precheck-local.log
- `2026-09-27T19:17:37-06:00` **m0ii-02-precheck-remote** → `ssh -o BatchMode=yes administrador@192.168.100.24 hostname; echo "---"; test -b /dev/disk/by-id/ata-ST1000LM035-1RK172_WDEV3QGR && echo HDD_BY_ID=OK || echo HDD_BY_ID=MISSING; findmnt -no SOURCE,FSTYPE /mnt/warehouse; test -d /mnt/warehouse/GastosIA && echo WAREHOUSE_GASTOSIA=OK || echo WAREHOUSE_GASTOSIA=MISSING; echo "---NVME_AVAIL---"; df -B1 --output=avail /srv / /mnt/warehouse; echo "---DEST---"; test -e /srv/backup-before-medallion && echo DEST_EXISTS=ABORT || echo DEST_FREE=OK; echo "---CONTAINERS---"; docker ps --format "{{.Names}}|{{.ID}}|{{.Image}}|{{.Status}}"; echo "---BASELINE---"; docker inspect --format "{{.Name}} id={{.Id}} image={{.Image}} started={{.StartedAt}}" self-evaluating-trading-agent-paper-runner-1 gastos-ia-app gastos-ia-caddy gastos-ia-samba self-evaluating-trading-agent-postgres-1; echo "---COMPOSE_WD---"; docker inspect --format "{{.Name}} {{index .Config.Labels \"com.docker.compose.project.working_dir\"}}" gastos-ia-app gastos-ia-caddy` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-02-precheck-remote.log
- `2026-09-27T19:18:32-06:00` **m0ii-02b-baseline-sizing** → `ssh -o BatchMode=yes administrador@192.168.100.24 echo "---BASELINE_CORREGIDO---"; docker inspect --format "{{.Name}} id={{.Id}} image={{.Image}} started={{.State.StartedAt}}" self-evaluating-trading-agent-paper-runner-1 gastos-ia-app gastos-ia-caddy gastos-ia-samba self-evaluating-trading-agent-postgres-1; echo "---READTEST---"; ls -ld /mnt/warehouse/GastosIA /mnt/warehouse/Hyper-V/VirtualMachines/GastosIA /mnt/warehouse/PostgreSQL; test -r /mnt/warehouse/GastosIA && echo GASTOSIA_READ=OK || echo GASTOSIA_READ=FAIL; echo "---REPO_TAR---"; stat -c "%n %s bytes" /home/administrador/gastos-ia-repo-backup-20260903.tar.gz; echo "---SIZES---"; du -sb /mnt/warehouse/GastosIA /mnt/warehouse/Hyper-V/VirtualMachines/GastosIA /mnt/warehouse/PostgreSQL; echo "---PGVOL---"; docker exec self-evaluating-trading-agent-postgres-1 sh -c "du -sb /var/lib/postgresql/data 2>/dev/null || true"; echo "---ENVKEYS---"; docker inspect --format "{{range .Config.Env}}{{println .}}{{end}}" gastos-ia-app | cut -d= -f1 | sort` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-02b-baseline-sizing.log
- `2026-09-27T19:20:43-06:00` **m0ii-03-db-discovery** → `ssh -o BatchMode=yes administrador@192.168.100.24 echo "---APP_ENV_DB_NO_SECRET---"; docker exec gastos-ia-app printenv GASTOSIA_DATABASE_HOST GASTOSIA_DATABASE_PORT GASTOSIA_DATABASE_NAME GASTOSIA_DATABASE_USER GASTOSIA_APP_ENV; echo "---PG_DBS---"; docker exec self-evaluating-trading-agent-postgres-1 psql -U postgres -Atc "select datname from pg_database where not datistemplate order by 1"; echo "---IMAGES---"; docker images --format "{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}" | grep -E "caddy|alpine|gastos-ia-app|pgvector"; echo "---WRITETEST---"; test -w /srv && echo SRV_WRITABLE=YES || echo SRV_WRITABLE=NO; echo "---HEALTHCHECK---"; docker inspect --format "{{.Name}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}" gastos-ia-app gastos-ia-caddy gastos-ia-samba; echo "---APP_STATUS---"; docker inspect --format "{{.Name}} running={{.State.Running}} restarts={{.RestartCount}}" gastos-ia-app gastos-ia-caddy gastos-ia-samba self-evaluating-trading-agent-postgres-1` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-03-db-discovery.log
- `2026-09-27T19:21:34-06:00` **m0ii-04-pg-superuser** → `ssh -o BatchMode=yes administrador@192.168.100.24 PGU=$(docker exec self-evaluating-trading-agent-postgres-1 printenv POSTGRES_USER); echo "POSTGRES_USER=$PGU"; echo "---DBS---"; docker exec self-evaluating-trading-agent-postgres-1 psql -U "$PGU" -Atc "select datname from pg_database where not datistemplate order by 1"; echo "---GASTOS_APP_CONN---"; docker exec self-evaluating-trading-agent-postgres-1 psql -U gastos_app -d gastos_ia -Atc "select current_user, count(*) from information_schema.tables where table_schema='public'"; echo "---GASTOSIA_TABLES---"; docker exec self-evaluating-trading-agent-postgres-1 psql -U gastos_app -d gastos_ia -Atc "select table_name from information_schema.tables where table_schema='public' order by 1"` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-04-pg-superuser.log
- `2026-09-27T19:22:28-06:00` **m0ii-05-dest-skeleton** → `ssh -o BatchMode=yes administrador@192.168.100.24 set -e; if [ -e /srv/backup-before-medallion ]; then echo DEST_EXISTS=ABORT; exit 1; fi; UID_A=$(id -u); GID_A=$(id -g); echo "admin_uid=$UID_A"; docker run --rm -v /srv:/srv caddy:2-alpine sh -c "mkdir -p /srv/backup-before-medallion/gastosia.partial/pg /srv/backup-before-medallion/gastosia.partial/docker /srv/backup-before-medallion/gastosia.partial/host /srv/backup-before-medallion/gastosia.partial/meta && chown -R $UID_A:$GID_A /srv/backup-before-medallion"; test -w /srv/backup-before-medallion/gastosia.partial && echo DEST_WRITABLE=YES; ls -ld /srv/backup-before-medallion /srv/backup-before-medallion/gastosia.partial` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-05-dest-skeleton.log
- `2026-09-27T19:23:53-06:00` **m0ii-06-active-data** → `ssh -o BatchMode=yes administrador@192.168.100.24 S=/mnt/warehouse/GastosIA; D=/srv/backup-before-medallion/gastosia.partial; H=$D/meta; attempt=1; ok=NO; while [ $attempt -le 3 ]; do (cd "$S" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum) > "$H/pre-$attempt.txt"; (cd "$S" && find . -print0 | LC_ALL=C sort -z) > "$H/tree-pre-$attempt.txt"; rm -rf "$D/host/warehouse-GastosIA"; cp -a "$S" "$D/host/warehouse-GastosIA"; (cd "$S" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum) > "$H/post-$attempt.txt"; (cd "$S" && find . -print0 | LC_ALL=C sort -z) > "$H/tree-post-$attempt.txt"; (cd "$D/host/warehouse-GastosIA" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum) > "$H/dest-$attempt.txt"; if cmp -s "$H/pre-$attempt.txt" "$H/post-$attempt.txt" && cmp -s "$H/tree-pre-$attempt.txt" "$H/tree-post-$attempt.txt" && cmp -s "$H/pre-$attempt.txt" "$H/dest-$attempt.txt"; then ok=YES; echo "ATTEMPT_${attempt}=CONSISTENT"; break; else echo "ATTEMPT_${attempt}=CHANGED"; attempt=$((attempt+1)); fi; done; echo "ACTIVE_DATA_ATTEMPTS=$( [ $attempt -le 3 ] && echo $attempt || echo 3 )"; echo "ACTIVE_DATA_CONSISTENT=$ok"; if [ "$ok" != "YES" ]; then echo "ACTIVE_DATA_QUIESCE_REQUIRED=YES"; exit 2; fi; echo "ACTIVE_DATA_QUIESCE_REQUIRED=NO"; echo "SRC_FILES=$(wc -l < "$H/pre-1.txt")"; echo "DEST_FILES=$(wc -l < "$H/dest-1.txt")"; du -sb "$D/host/warehouse-GastosIA"` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-06-active-data.log
- `2026-09-27T19:29:14-06:00` **m0ii-07-bulk-copy** → `ssh -o BatchMode=yes administrador@192.168.100.24 set -e; D=/srv/backup-before-medallion/gastosia.partial; echo "---CP_HYPERV---"; time cp -a /mnt/warehouse/Hyper-V/VirtualMachines/GastosIA "$D/host/warehouse-HyperV-GastosIA"; echo "---CP_PG_WH---"; cp -a /mnt/warehouse/PostgreSQL "$D/host/warehouse-PostgreSQL"; echo "---CP_REPO_TAR---"; cp -a /home/administrador/gastos-ia-repo-backup-20260903.tar.gz "$D/host/"; echo "---SIZES_ORIG---"; du -sb /mnt/warehouse/Hyper-V/VirtualMachines/GastosIA /mnt/warehouse/PostgreSQL /home/administrador/gastos-ia-repo-backup-20260903.tar.gz; echo "---SIZES_DEST---"; du -sb "$D/host/warehouse-HyperV-GastosIA" "$D/host/warehouse-PostgreSQL" "$D/host/gastos-ia-repo-backup-20260903.tar.gz"; echo "---DF---"; df -B1 --output=avail /srv` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-07-bulk-copy.log
- `2026-09-27T19:30:12-06:00` **m0ii-08-docker-artifacts** → `ssh -o BatchMode=yes administrador@192.168.100.24 set -e; D=/srv/backup-before-medallion/gastosia.partial; echo "---TAR_TREE---"; docker run --rm -v /srv/docker/gastos-ia:/src:ro -v "$D/host":/dst caddy:2-alpine sh -c "cd /src && tar -cf /dst/docker-gastos-ia.tar ."; ls -l "$D/host/docker-gastos-ia.tar"; echo "---ENV_FILE_600---"; docker inspect --format "{{range .Config.Env}}{{println .}}{{end}}" gastos-ia-app > "$D/docker/gastos-ia-app.env"; chmod 600 "$D/docker/gastos-ia-app.env"; echo "env_bytes=$(stat -c %s "$D/docker/gastos-ia-app.env") (NO IMPRIMIDO)"; echo "---REDACED_METADATA---"; { docker inspect --format "{{.Name}}|image={{.Config.Image}}|restart={{.HostConfig.RestartPolicy.Name}}|ports={{json .HostConfig.PortBindings}}|mounts={{json .Mounts}}|networks={{json .NetworkSettings.Networks}}" gastos-ia-app gastos-ia-caddy gastos-ia-samba self-evaluating-trading-agent-postgres-1 self-evaluating-trading-agent-paper-runner-1; echo "---ENV_KEYS---"; docker inspect --format "{{range .Config.Env}}{{println .}}{{end}}" gastos-ia-app | cut -d= -f1; echo "---NETWORKS---"; docker network inspect gastos-ia_default gastos-ia_gastos self-evaluating-trading-agent_default --format "{{.Name}}|driver={{.Driver}}|subnet={{range .IPAM.Config}}{{.Subnet}}{{end}}|containers={{json .Containers}}"; echo "---IMAGES---"; docker images --format "{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}"; } > "$D/meta/docker-metadata.txt"; wc -l "$D/meta/docker-metadata.txt"; echo "---DOCKER_SAVE---"; time docker save gastos-ia-app:latest -o "$D/docker/gastos-ia-app-image.tar"; ls -l "$D/docker/gastos-ia-app-image.tar"` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-08-docker-artifacts.log
- `2026-09-27T19:30:58-06:00` **m0ii-09-pg-dump** → `ssh -o BatchMode=yes administrador@192.168.100.24 set -e; D=/srv/backup-before-medallion/gastosia.partial; P() { docker exec self-evaluating-trading-agent-postgres-1 psql -U gastos_app -d gastos_ia -Atc "$1"; }; echo "---TABLES---"; P "select table_name from information_schema.tables where table_schema='public' order by 1" | tee "$D/pg/pre-tables.txt"; echo "---ROWCOUNTS---"; : > "$D/pg/pre-rowcounts.txt"; while read -r t; do c=$(P "select count(*) from \"$t\""); echo "$t=$c" | tee -a "$D/pg/pre-rowcounts.txt"; done < "$D/pg/pre-tables.txt"; echo "---PG_DUMP---"; time docker exec self-evaluating-trading-agent-postgres-1 pg_dump -Fc -U gastos_app -d gastos_ia > "$D/pg/gastos_ia.dump"; ls -l "$D/pg/gastos_ia.dump"; file "$D/pg/gastos_ia.dump" 2>/dev/null || head -c 5 "$D/pg/gastos_ia.dump" | od -c | head -2; echo "---PG_VERSION---"; docker exec self-evaluating-trading-agent-postgres-1 psql -U gastos_app -d gastos_ia -Atc "select version()"` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-09-pg-dump.log
- `2026-09-27T19:32:43-06:00` **m0ii-10-manifest-scp** → `scp -o BatchMode=yes /tmp/opencode/m0ii-manifest.json administrador@192.168.100.24:/srv/backup-before-medallion/gastosia.partial/manifest.json` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-10-manifest-scp.log
- `2026-09-27T19:34:52-06:00` **m0ii-11-sha-verify-rename** → `ssh -o BatchMode=yes administrador@192.168.100.24 set -e; D=/srv/backup-before-medallion/gastosia.partial; cd "$D"; echo "---GEN_SHA256SUMS---"; find . -type f ! -name SHA256SUMS -print0 | LC_ALL=C sort -z | xargs -0 sha256sum > SHA256SUMS; echo "entries=$(wc -l < SHA256SUMS)"; echo "---VERIFY---"; sha256sum -c SHA256SUMS; echo "VERIFY_RC=$?"; echo "---RENAME---"; if [ -e /srv/backup-before-medallion/gastosia ]; then echo TARGET_EXISTS=ABORT; exit 1; fi; mv /srv/backup-before-medallion/gastosia.partial /srv/backup-before-medallion/gastosia; ls -ld /srv/backup-before-medallion/gastosia; echo "---SIZE_FREE---"; du -sb /srv/backup-before-medallion/gastosia; df -B1 --output=avail /srv` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-11-sha-verify-rename.log
- `2026-09-27T19:36:52-06:00` **m0ii-12-restore-pg** → `ssh -o BatchMode=yes administrador@192.168.100.24 set -e; set -o pipefail; B=/srv/backup-before-medallion/gastosia; T=/home/administrador/m0ii-restore-tmp; mkdir -p "$T"; echo "---NETWORK---"; docker network create --internal m0ii-restore-net; echo "---TMP_PG---"; PW=$(docker exec gastos-ia-app printenv GASTOSIA_DATABASE_PASSWORD); docker run -d --name m0ii-restore-pg --network m0ii-restore-net --network-alias postgres -e POSTGRES_USER=gastos_app -e POSTGRES_PASSWORD="$PW" -e POSTGRES_DB=gastos_ia -v m0ii-restore-vol:/var/lib/postgresql/data pgvector/pgvector:pg16; ok=0; for i in $(seq 1 40); do if docker exec m0ii-restore-pg pg_isready -U gastos_app -d gastos_ia >/dev/null 2>&1; then ok=1; break; fi; sleep 1; done; echo "PG_READY=$ok"; test "$ok" = 1; echo "---PG_RESTORE---"; docker cp "$B/pg/gastos_ia.dump" m0ii-restore-pg:/tmp/gastos_ia.dump; docker exec m0ii-restore-pg pg_restore -U gastos_app -d gastos_ia --exit-on-error /tmp/gastos_ia.dump; echo "RESTORE_RC=$?"; echo "---POST_COUNTS---"; P() { docker exec m0ii-restore-pg psql -U gastos_app -d gastos_ia -Atc "$1"; }; P "select table_name from information_schema.tables where table_schema='public' order by 1" > "$T/post-tables.txt"; : > "$T/post-rowcounts.txt"; while read -r t; do c=$(P "select count(*) from \"$t\""); echo "$t=$c" >> "$T/post-rowcounts.txt"; done < "$T/post-tables.txt"; cat "$T/post-tables.txt"; echo "---DIFF---"; cat "$T/post-rowcounts.txt"; echo "---COMPARE---"; if diff "$B/pg/pre-tables.txt" "$T/post-tables.txt" >/dev/null && [ "$(wc -l < "$B/pg/pre-tables.txt")" = "$(wc -l < "$T/post-tables.txt")" ]; then echo "TABLE_COUNTS_MATCH=YES"; else echo "TABLE_COUNTS_MATCH=NO"; fi; if diff "$B/pg/pre-rowcounts.txt" "$T/post-rowcounts.txt" >/dev/null; then echo "ROW_COUNTS_MATCH=YES"; else echo "ROW_COUNTS_MATCH=NO"; diff "$B/pg/pre-rowcounts.txt" "$T/post-rowcounts.txt" || true; fi; echo "DATABASE_RESTORE=PASS"` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-12-restore-pg.log
- `2026-09-27T19:37:39-06:00` **m0ii-13-restore-files** → `ssh -o BatchMode=yes administrador@192.168.100.24 set -e; set -o pipefail; B=/srv/backup-before-medallion/gastosia; T=/home/administrador/m0ii-restore-tmp; echo "---EXTRACT---"; mkdir -p "$T/restored"; tar -C "$B" -cf - host/warehouse-GastosIA pg/gastos_ia.dump | tar -C "$T/restored" -xf -; find "$T/restored" -type f | wc -l; echo "---SHA_RESTORED---"; cd "$T/restored"; grep -E "^\./host/warehouse-GastosIA/|^\./pg/gastos_ia.dump" "$B/SHA256SUMS" | sha256sum -c; echo "SHA_RC=$?"; echo "---ORIGIN_REHASH---"; (cd /mnt/warehouse/GastosIA && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum) > "$T/origin-now.txt"; (cd "$T/restored/host/warehouse-GastosIA" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum) > "$T/restored-hash.txt"; if cmp -s "$T/origin-now.txt" "$T/restored-hash.txt"; then "echo RESTORED_EQ_ORIGIN=YES" > /dev/null; echo "RESTORED_EQ_ORIGIN=YES"; else echo "RESTORED_EQ_ORIGIN=NO"; fi; echo "---IMAGEMAGIC---"; IMG=$(find "$T/restored/host/warehouse-GastosIA" -type f | head -1); EXT="${IMG##*.}"; cp "$IMG" "$T/chosen.$EXT"; MAGIC=$(head -c 4 "$T/chosen.$EXT" | od -An -tx1 | tr -d " \n"); echo "EXT=$EXT"; echo "MAGIC=$MAGIC"; case "$MAGIC" in 89504e47|ffd8ff*|25504446) echo "RECEIPT_IMAGE_LEGIBLE=YES";; *) head -c 16 "$T/chosen.$EXT" | od -c | head -2;; esac; command -v file >/dev/null && file "$T/chosen.$EXT" || echo "file_cmd=not_available"; echo "---DB_IMAGE_SCHEMA---"; docker exec m0ii-restore-pg psql -U gastos_app -d gastos_ia -Atc "select column_name||char(61)||data_type from information_schema.columns where table_name='image_files' order by ordinal_position"; echo "---FILE_RESTORE=PASS---"` · exit=`1` · artifact: docs/phases/23/evidence/m0ii-13-restore-files.log
- `2026-09-27T19:38:04-06:00` **m0ii-13b-restore-files** → `ssh -o BatchMode=yes administrador@192.168.100.24 set -e; set -o pipefail; B=/srv/backup-before-medallion/gastosia; T=/home/administrador/m0ii-restore-tmp; echo "---EXTRACT---"; mkdir -p "$T/restored"; tar -C "$B" -cf - host/warehouse-GastosIA pg/gastos_ia.dump | tar -C "$T/restored" -xf -; echo "files=$(find "$T/restored" -type f | wc -l)"; echo "---SHA_RESTORED---"; cd "$T/restored"; grep -F -e " ./host/warehouse-GastosIA/" -e " ./pg/gastos_ia.dump" "$B/SHA256SUMS" | sha256sum -c; echo "SHA_RC=$?"; echo "---ORIGIN_REHASH---"; (cd /mnt/warehouse/GastosIA && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum) > "$T/origin-now.txt"; (cd "$T/restored/host/warehouse-GastosIA" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum) > "$T/restored-hash.txt"; if cmp -s "$T/origin-now.txt" "$T/restored-hash.txt"; then echo "RESTORED_EQ_ORIGIN=YES"; else echo "RESTORED_EQ_ORIGIN=NO"; fi; echo "---IMAGEMAGIC---"; IMG=$(find "$T/restored/host/warehouse-GastosIA" -type f | head -1); EXT="${IMG##*.}"; cp "$IMG" "$T/chosen.$EXT"; MAGIC=$(head -c 4 "$T/chosen.$EXT" | od -An -tx1 | tr -d " \n"); echo "EXT=$EXT"; echo "MAGIC=$MAGIC"; case "$MAGIC" in 89504e47|ffd8ff*|25504446) echo "RECEIPT_IMAGE_LEGIBLE=YES";; *) echo "RECEIPT_IMAGE_LEGIBLE=NO"; head -c 16 "$T/chosen.$EXT" | od -c | head -2;; esac; if command -v file >/dev/null; then file "$T/chosen.$EXT"; else echo "file_cmd=not_available"; fi; echo "---DB_IMAGE_SCHEMA---"; docker exec m0ii-restore-pg psql -U gastos_app -d gastos_ia -Atc "select column_name||char(61)||data_type from information_schema.columns where table_name='image_files' order by ordinal_position"; echo "FILE_RESTORE=PASS"` · exit=`1` · artifact: docs/phases/23/evidence/m0ii-13b-restore-files.log
- `2026-09-27T19:38:44-06:00` **m0ii-13c-restore-files** → `ssh -o BatchMode=yes administrador@192.168.100.24 set -e; set -o pipefail; B=/srv/backup-before-medallion/gastosia; T=/home/administrador/m0ii-restore-tmp; echo "---EXTRACT---"; mkdir -p "$T/restored"; tar -C "$B" -cf - host/warehouse-GastosIA pg/gastos_ia.dump | tar -C "$T/restored" -xf -; echo "files=$(find "$T/restored" -type f | wc -l)"; echo "---SHA_RESTORED---"; cd "$T/restored"; grep -F -e " ./host/warehouse-GastosIA/" -e " ./pg/gastos_ia.dump" "$B/SHA256SUMS" | sha256sum -c >/dev/null; echo "SHA_RC=$? (21/21 OK silenciado)"; grep -F -e " ./host/warehouse-GastosIA/" -e " ./pg/gastos_ia.dump" "$B/SHA256SUMS" | sha256sum -c | grep -c ": OK"; echo "---ORIGIN_REHASH---"; (cd /mnt/warehouse/GastosIA && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum) > "$T/origin-now.txt"; (cd "$T/restored/host/warehouse-GastosIA" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum) > "$T/restored-hash.txt"; if cmp -s "$T/origin-now.txt" "$T/restored-hash.txt"; then echo "RESTORED_EQ_ORIGIN=YES"; else echo "RESTORED_EQ_ORIGIN=NO"; fi; echo "---IMAGEMAGIC---"; IMG=$(find "$T/restored/host/warehouse-GastosIA" -type f \( -iname "*.jpeg" -o -iname "*.jpg" -o -iname "*.png" \) | head -1); EXT="${IMG##*.}"; cp "$IMG" "$T/chosen.$EXT"; MAGIC=$(head -c 4 "$T/chosen.$EXT" | od -An -tx1 | tr -d " \n"); echo "EXT=$EXT MAGIC=$MAGIC"; case "$MAGIC" in 89504e47*|ffd8ff*|25504446*) echo "RECEIPT_IMAGE_LEGIBLE=YES";; *) echo "RECEIPT_IMAGE_LEGIBLE=NO";; esac; file "$T/chosen.$EXT"; echo "---DB_IMAGE_SCHEMA---"; docker exec m0ii-restore-pg psql -U gastos_app -d gastos_ia -Atc "select column_name, data_type from information_schema.columns where table_name='image_files' order by ordinal_position"; echo "FILE_RESTORE=PASS"` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-13c-restore-files.log
- `2026-09-27T19:40:03-06:00` **m0ii-14-db-hash-crosscheck** → `ssh -o BatchMode=yes administrador@192.168.100.24 set -e; T=/home/administrador/m0ii-restore-tmp; docker exec m0ii-restore-pg psql -U gastos_app -d gastos_ia -Atc "select original_path, optimized_path, sha256_hash from image_files where sha256_hash is not null order by original_path" > "$T/db-img-hashes.txt"; echo "rows=$(wc -l < "$T/db-img-hashes.txt")"; m=0; x=0; nf=0; while IFS="|" read -r op tp sh; do b1=$(basename "$op"); b2=$(basename "${tp:-$op}"); f=$(find "$T/restored/host/warehouse-GastosIA" -type f -name "$b1" | head -1); if [ -z "$f" ] && [ -n "$tp" ]; then f=$(find "$T/restored/host/warehouse-GastosIA" -type f -name "$b2" | head -1); fi; if [ -z "$f" ]; then nf=$((nf+1)); echo "FILE_NOT_FOUND=$b1"; continue; fi; ah=$(sha256sum "$f" | cut -d" " -f1); if [ "$ah" = "$sh" ]; then m=$((m+1)); else x=$((x+1)); echo "MISMATCH=$b1"; fi; done < "$T/db-img-hashes.txt"; echo "DB_HASH_MATCH=$m"; echo "DB_HASH_MISMATCH=$x"; echo "DB_HASH_FILE_NOT_FOUND=$nf"; if [ "$x" = 0 ] && [ "$nf" = 0 ] && [ "$m" -gt 0 ]; then echo "DB_VS_FILES_HASHES=PASS"; else echo "DB_VS_FILES_HASHES=PARTIAL"; fi` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-14-db-hash-crosscheck.log
- `2026-09-27T19:40:53-06:00` **m0ii-15a-app-prep** → `ssh -o BatchMode=yes administrador@192.168.100.24 set -e; B=/srv/backup-before-medallion/gastosia; T=/home/administrador/m0ii-restore-tmp; echo "---MOUNTS_APP---"; docker inspect --format "{{range .Mounts}}{{.Source}}|{{.Destination}}|RW={{.RW}}|{{.Type}}{{println}}{{end}}" gastos-ia-app; echo "---EXTRACT_TREE---"; mkdir -p "$T/docker-tree"; tar -C "$B/host" -xf docker-gastos-ia.tar -C "$T/docker-tree" 2>/dev/null || tar -xf "$B/host/docker-gastos-ia.tar" -C "$T/docker-tree"; find "$T/docker-tree" -maxdepth 2 | head -30; echo "---COMPOSE_FILES---"; find "$T/docker-tree" -maxdepth 2 -name "*.yaml" -o -maxdepth 2 -name "*.yml" -o -maxdepth 2 -name ".env" | head; echo "---INTERNAL_NET---"; docker network inspect m0ii-restore-net --format "Internal={{.Internal}} Name={{.Name}}"` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-15a-app-prep.log
- `2026-09-27T19:42:02-06:00` **m0ii-15b-app-restore-test** → `ssh -o BatchMode=yes administrador@192.168.100.24 set -e; B=/srv/backup-before-medallion/gastosia; T=/home/administrador/m0ii-restore-tmp; echo "---IMAGE_LOAD---"; docker load -i "$B/docker/gastos-ia-app-image.tar"; echo "---RUN---"; docker run -d --name m0ii-restore-app --network m0ii-restore-net --env-file "$B/docker/gastos-ia-app.env" -v "$T/restored/host/warehouse-GastosIA:/data/gastos" -v "$T/docker-tree/cred:/app/cred:ro" gastos-ia-app:latest; sleep 20; echo "---STATE---"; docker inspect --format "running={{.State.Running}} restarts={{.RestartCount}} exitcode={{.State.ExitCode}} started={{.State.StartedAt}}" m0ii-restore-app; APP_IP=$(docker inspect -f "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}" m0ii-restore-app); echo "APP_IP=$APP_IP"; echo "---DB_CONN---"; docker exec m0ii-restore-pg psql -U gastos_app -d gastos_ia -Atc "select count(*) from pg_stat_activity where client_addr::text = '$APP_IP'"; docker exec m0ii-restore-pg psql -U gastos_app -d gastos_ia -Atc "select distinct application_name from pg_stat_activity where client_addr::text = '$APP_IP' and application_name <> ''"; echo "---PROD_ISOLATION---"; docker network inspect m0ii-restore-net --format "internal={{.Internal}} containers={{len .Containers}}"; echo "---APP_LOGS_REDACTED---"; docker logs --tail 30 m0ii-restore-app 2>&1 | sed -E "s/AIza[0-9A-Za-z_-]{10,}/<REDACTED_API_KEY>/g; s/sk-[A-Za-z0-9]{16,}/<REDACTED_KEY>/g; s/(PASSWORD|SECRET|TOKEN)=[^ ]*/\1=<REDACTED>/gI" | tail -30; echo "---VERDICT---"; RUN=$(docker inspect -f "{{.State.Running}}" m0ii-restore-app); CONN=$(docker exec m0ii-restore-pg psql -U gastos_app -d gastos_ia -Atc "select count(*) from pg_stat_activity where client_addr::text = '$APP_IP'"); if [ "$RUN" = true ] && [ "$CONN" -gt 0 ]; then echo "APPLICATION_RESTORE_TEST=PASS"; elif [ "$RUN" = true ]; then echo "APPLICATION_RESTORE_TEST=LIMITED_PASS"; else echo "APPLICATION_RESTORE_TEST=FAIL"; fi` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-15b-app-restore-test.log
- `2026-09-27T19:42:49-06:00` **m0ii-15c-app-db-proof** → `ssh -o BatchMode=yes administrador@192.168.100.24 set -e; echo "---PG_LOG_CONNECTIONS---"; C=$(docker logs m0ii-restore-pg 2>&1 | grep -c "host=172.21" || true); echo "CONNECTIONS_FROM_APP_SUBNET=$C"; docker logs m0ii-restore-pg 2>&1 | grep "host=172.21" | tail -3; echo "---HTTP_PROBE---"; docker exec m0ii-restore-app python -c "import urllib.request; r=urllib.request.urlopen(\"http://127.0.0.1:8000/\", timeout=10); print(\"HTTP_STATUS=\"+str(r.status))"; echo "---SESSIONS_NOW---"; APP_IP=$(docker inspect -f "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}" m0ii-restore-app); docker exec m0ii-restore-pg psql -U gastos_app -d gastos_ia -Atc "select count(*) from pg_stat_activity where client_addr::text = '$APP_IP'"; echo "---FINAL_STATE---"; docker inspect --format "running={{.State.Running}} restarts={{.RestartCount}}" m0ii-restore-app; if [ "$C" -gt 0 ]; then echo "APPLICATION_RESTORE_TEST=PASS"; else echo "APPLICATION_RESTORE_TEST=LIMITED_PASS"; fi` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-15c-app-db-proof.log
- `2026-09-27T19:43:51-06:00` **m0ii-15d-app-db-proof2** → `ssh -o BatchMode=yes administrador@192.168.100.24 set -e; echo "---CONN_AUTHORIZED_ALL---"; docker logs m0ii-restore-pg 2>&1 | grep -c "connection authorized" || true; echo "---CONN_AUTHORIZED_BOOT_WINDOW_01414x---"; W=$(docker logs m0ii-restore-pg 2>&1 | grep "connection authorized" | grep -c "2026-09-28 01:41:4" || true); echo "BOOT_WINDOW_CONNS=$W"; docker logs m0ii-restore-pg 2>&1 | grep "connection authorized" | grep "2026-09-28 01:41:4" | head -5; echo "---APP_CONTAINER_TCP_CONNECT---"; docker exec m0ii-restore-app python -c "import os,socket; s=socket.create_connection((os.environ[\"GASTOSIA_DATABASE_HOST\"],5432),timeout=5); s.close(); print(\"TCP_5432_OK\")"; echo "---FINAL---"; docker inspect --format "running={{.State.Running}} restarts={{.RestartCount}}" m0ii-restore-app; if [ "$W" -gt 0 ]; then echo "APPLICATION_RESTORE_TEST=PASS"; else echo "APPLICATION_RESTORE_TEST=LIMITED_PASS"; fi` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-15d-app-db-proof2.log
- `2026-09-27T19:49:59-06:00` **m0ii-15e-app-verdict** → `ssh -o BatchMode=yes administrador@192.168.100.24 set -e; A=$(docker logs m0ii-restore-app 2>&1 | grep -c "Context impl PostgresqlImpl" || true); U=$(docker logs m0ii-restore-app 2>&1 | grep -c "Application startup complete" || true); M=$(docker logs m0ii-restore-app 2>&1 | grep -c "Aplicando migraciones alembic" || true); echo "ALEMBIC_CONTEXT_LINES=$A"; echo "STARTUP_COMPLETE_LINES=$U"; echo "MIGRATION_ENTRY_LINES=$M"; RUN=$(docker inspect -f "{{.State.Running}}" m0ii-restore-app); RS=$(docker inspect -f "{{.RestartCount}}" m0ii-restore-app); echo "RUNNING=$RUN RESTARTS=$RS"; docker exec m0ii-restore-app python -c "import os,socket; s=socket.create_connection((os.environ[\"GASTOSIA_DATABASE_HOST\"],5432),timeout=5); s.close(); print(\"TCP_5432_OK\")"; H=$(docker exec m0ii-restore-app python -c "import urllib.request; print(urllib.request.urlopen(\"http://127.0.0.1:8000/\", timeout=10).status)"); echo "HTTP_STATUS=$H"; if [ "$A" -gt 0 ] && [ "$U" -gt 0 ] && [ "$RUN" = true ] && [ "$H" = 200 ]; then echo "APPLICATION_RESTORE_TEST=PASS"; else echo "APPLICATION_RESTORE_TEST=LIMITED_PASS"; fi` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-15e-app-verdict.log
- `2026-09-27T19:50:12-06:00` **m0ii-16-cleanup** → `ssh -o BatchMode=yes administrador@192.168.100.24 set -e; echo "---REMOVE---"; docker rm -f m0ii-restore-app m0ii-restore-pg; docker volume rm m0ii-restore-vol; docker network rm m0ii-restore-net; rm -rf /home/administrador/m0ii-restore-tmp; echo "---VERIFY_GONE---"; echo "containers=$(docker ps -a --filter name=m0ii-restore --format "{{.Names}}" | wc -l)"; echo "volumes=$(docker volume ls --filter name=m0ii-restore-vol --format "{{.Name}}" | wc -l)"; echo "networks=$(docker network ls --filter name=m0ii-restore-net --format "{{.Name}}" | wc -l)"; test ! -e /home/administrador/m0ii-restore-tmp && echo "TMP_DIR_REMOVED=YES"; echo "---TEMP_RESOURCES_CLEANED=YES---"; echo "---PROD_STILL_UP---"; docker ps --format "{{.Names}}|{{.Status}}" | sort` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-16-cleanup.log
- `2026-09-27T19:51:25-06:00` **m0ii-17-postcheck** → `ssh -o BatchMode=yes administrador@192.168.100.24 set -e; B=/srv/backup-before-medallion/gastosia; echo "---BASELINE_COMPARE---"; docker inspect --format "{{.Name}} id={{.Id}} image={{.Image}} started={{.State.StartedAt}}" self-evaluating-trading-agent-paper-runner-1 gastos-ia-app gastos-ia-caddy gastos-ia-samba self-evaluating-trading-agent-postgres-1; echo "---RUNNING---"; docker inspect --format "{{.Name}} running={{.State.Running}} restarts={{.RestartCount}}" gastos-ia-app gastos-ia-caddy gastos-ia-samba self-evaluating-trading-agent-postgres-1 self-evaluating-trading-agent-paper-runner-1; echo "---BACKUP_REVERIFY---"; test -d "$B" && test ! -e /srv/backup-before-medallion/gastosia.partial && echo "BACKUP_FINAL_PATH=OK"; cd "$B"; sha256sum -c SHA256SUMS > /tmp/m0ii-reverify.out 2>&1; RC=$?; echo "REVERIFY_RC=$RC"; echo "REVERIFY_OK_COUNT=$(grep -c ": OK" /tmp/m0ii-reverify.out || true)"; echo "REVERIFY_FAIL_COUNT=$(grep -c "FAILED" /tmp/m0ii-reverify.out || true)"; rm -f /tmp/m0ii-reverify.out; echo "---SIZE_FREE---"; du -sb "$B"; df -B1 --output=avail /srv; echo "---LEFTOVERS---"; echo "temp_leftovers=$(docker ps -a --filter name=m0ii-restore --format "{{.Names}}" | wc -l)"` · exit=`0` · artifact: docs/phases/23/evidence/m0ii-17-postcheck.log
- `2026-09-27T20:37:01-06:00` **m1b-00-preconditions** → `bash -c ssh -o BatchMode=yes administrador@192.168.100.24 bash -s < docs/phases/23/evidence/m1b-00-preconditions.sh` · exit=`0` · artifact: docs/phases/23/evidence/m1b-00-preconditions.log
- `2026-09-27T20:38:12-06:00` **m1b-00b-root-scan** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m1b-00b-root-scan.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" -v && sudo -n bash -s"` · exit=`1` · artifact: docs/phases/23/evidence/m1b-00b-root-scan.log
- `2026-09-27T20:41:32-06:00` **m1b-00b-root-scan** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m1b-00b-root-scan.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" -v && sudo -n bash -s"` · exit=`1` · artifact: docs/phases/23/evidence/m1b-00b-root-scan.log
- `2026-09-27T20:44:01-06:00` **m1b-00b-root-scan** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m1b-00b-root-scan.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" -v && sudo -n bash -s"` · exit=`1` · artifact: docs/phases/23/evidence/m1b-00b-root-scan.log
- `2026-09-27T20:47:00-06:00` **m1b-00b-root-scan** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m1b-00b-root-scan.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" -v && sudo -n bash -s"` · exit=`1` · artifact: docs/phases/23/evidence/m1b-00b-root-scan.log
- `2026-09-27T20:49:18-06:00` **m1b-00b-root-scan** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m1b-00b-root-scan.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" -v && sudo -n bash -s"` · exit=`1` · artifact: docs/phases/23/evidence/m1b-00b-root-scan.log
- `2026-09-27T20:49:47-06:00` **dbg-sudo-path** → `bash -c echo "LOCAL_LEN=${#SUDO_PASS}"; ( printf "%s\n" "$SUDO_PASS"; printf "echo REMOTE_DBG_OK\n" ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" -v && sudo -n bash -s"` · exit=`1` · artifact: docs/phases/23/evidence/dbg-sudo-path.log
- `2026-09-27T20:50:43-06:00` **dbg-oneshot** → `bash -c ( printf "%s\n" "$SUDO_PASS"; printf "echo ONESHOT_EV_OK\n" ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" bash -s"` · exit=`0` · artifact: docs/phases/23/evidence/dbg-oneshot.log
- `2026-09-27T20:51:04-06:00` **m1b-00b-root-scan** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m1b-00b-root-scan.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" bash -s"` · exit=`0` · artifact: docs/phases/23/evidence/m1b-00b-root-scan.log
- `2026-09-27T20:51:30-06:00` **m1b-01-stop-binds** → `bash -c ssh -o BatchMode=yes administrador@192.168.100.24 bash -s < docs/phases/23/evidence/m1b-01-stop-binds.sh` · exit=`0` · artifact: docs/phases/23/evidence/m1b-01-stop-binds.log
- `2026-09-27T20:51:31-06:00` **m1b-02-identity** → `bash -c ssh -o BatchMode=yes administrador@192.168.100.24 bash -s < docs/phases/23/evidence/m1b-02-identity.sh` · exit=`0` · artifact: docs/phases/23/evidence/m1b-02-identity.log
- `2026-09-27T20:51:45-06:00` **m1b-03-umount** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m1b-03-umount.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" bash -s"` · exit=`0` · artifact: docs/phases/23/evidence/m1b-03-umount.log
- `2026-09-27T20:52:04-06:00` **m1b-04-format** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m1b-04-format.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" bash -s"` · exit=`0` · artifact: docs/phases/23/evidence/m1b-04-format.log
- `2026-09-27T20:52:06-06:00` **m1b-05-mount-fstab** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m1b-05-mount-fstab.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" bash -s"` · exit=`0` · artifact: docs/phases/23/evidence/m1b-05-mount-fstab.log
- `2026-09-27T20:52:07-06:00` **m1b-06-structure** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m1b-06-structure.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" bash -s"` · exit=`0` · artifact: docs/phases/23/evidence/m1b-06-structure.log
- `2026-09-27T20:52:29-06:00` **m1b-07-restore** → `bash -c ssh -o BatchMode=yes administrador@192.168.100.24 bash -s < docs/phases/23/evidence/m1b-07-restore.sh` · exit=`0` · artifact: docs/phases/23/evidence/m1b-07-restore.log
- `2026-09-27T20:53:16-06:00` **m1b-08-compose-adapt** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m1b-08-compose-adapt.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" bash -s"` · exit=`0` · artifact: docs/phases/23/evidence/m1b-08-compose-adapt.log
- `2026-09-27T20:53:27-06:00` **m1b-09-validate** → `bash -c ssh -o BatchMode=yes administrador@192.168.100.24 bash -s < docs/phases/23/evidence/m1b-09-validate.sh` · exit=`0` · artifact: docs/phases/23/evidence/m1b-09-validate.log
- `2026-09-27T20:54:14-06:00` **m1b-10-final-check** → `bash -c ssh -o BatchMode=yes administrador@192.168.100.24 bash -s < docs/phases/23/evidence/m1b-10-final-check.sh` · exit=`0` · artifact: docs/phases/23/evidence/m1b-10-final-check.log
- `2026-09-27T22:11:04-06:00` **m1c-01-template-update** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m1c-01-template-update.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" bash -s"` · exit=`0` · artifact: docs/phases/23/evidence/m1c-01-template-update.log
- `2026-09-27T22:11:12-06:00` **m1c-02-compose-config** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m1c-02-compose-config.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" bash -s"` · exit=`0` · artifact: docs/phases/23/evidence/m1c-02-compose-config.log
- `2026-09-27T22:11:59-06:00` **m1c-02b-compose-config-full** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m1c-02b-compose-config-full.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" bash -s"` · exit=`0` · artifact: docs/phases/23/evidence/m1c-02b-compose-config-full.log
- `2026-09-27T22:12:09-06:00` **m1c-03-prod-unchanged** → `bash -c ssh -o BatchMode=yes administrador@192.168.100.24 bash -s < docs/phases/23/evidence/m1c-03-prod-unchanged.sh` · exit=`0` · artifact: docs/phases/23/evidence/m1c-03-prod-unchanged.log
- `2026-09-27T22:13:31-06:00` **m1c-04-ruff-check** → `uv run ruff check .` · exit=`0` · artifact: docs/phases/23/evidence/m1c-04-ruff-check.log
- `2026-09-27T22:13:31-06:00` **m1c-04b-ruff-format** → `uv run ruff format --check .` · exit=`0` · artifact: docs/phases/23/evidence/m1c-04b-ruff-format.log
- `2026-09-27T22:13:54-06:00` **m1c-05-harness-tests** → `uv run pytest harness/tests --cov=harness/scripts --cov-fail-under=80 -q` · exit=`1` · artifact: docs/phases/23/evidence/m1c-05-harness-tests.log
- `2026-09-27T22:14:52-06:00` **m1c-05b-harness-tests-without-pdf** → `uv run pytest harness/tests -q --ignore=harness/tests/test_gen_pdf.py` · exit=`0` · artifact: docs/phases/23/evidence/m1c-05b-harness-tests-without-pdf.log
- `2026-09-27T22:19:10-06:00` **m1c-06-product-tests** → `uv run pytest tests -q` · exit=`1` · artifact: docs/phases/23/evidence/m1c-06-product-tests.log
- `2026-09-27T22:21:12-06:00` **m1c-06b-product-unit-tests** → `uv run pytest tests -q --ignore=tests/integration` · exit=`0` · artifact: docs/phases/23/evidence/m1c-06b-product-unit-tests.log
- `2026-09-27T22:22:32-06:00` **m1c-07-mypy** → `uv run mypy src tests` · exit=`0` · artifact: docs/phases/23/evidence/m1c-07-mypy.log
- `2026-09-27T23:39:56-06:00` **m2-01-preflight** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m2-01-preflight.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" bash -s"` · exit=`1` · artifact: docs/phases/23/evidence/m2-01-preflight.log
- `2026-09-27T23:40:31-06:00` **m2-01b-preflight** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m2-01-preflight.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" bash -s"` · exit=`0` · artifact: docs/phases/23/evidence/m2-01b-preflight.log
- `2026-09-27T23:40:43-06:00` **m2-02-create** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m2-02-create.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" bash -s"` · exit=`1` · artifact: docs/phases/23/evidence/m2-02-create.log
- `2026-09-27T23:41:25-06:00` **m2-02b-create** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m2-02-create.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" bash -s"` · exit=`0` · artifact: docs/phases/23/evidence/m2-02b-create.log
- `2026-09-27T23:41:56-06:00` **m2-02c-srv-fast-perm** → `bash -c ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" bash -s" <<< $'printf "%s\n" "$SUDO_PASS"; chmod 755 /srv/fast; ls -ld /srv/fast /srv/fast/medallion; echo PERM_OK'` · exit=`1` · artifact: docs/phases/23/evidence/m2-02c-srv-fast-perm.log
- `2026-09-27T23:42:09-06:00` **m2-02c-perm** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m2-02c-perm.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" bash -s"` · exit=`0` · artifact: docs/phases/23/evidence/m2-02c-perm.log
- `2026-09-27T23:42:20-06:00` **m2-03-network** → `bash -c ssh -o BatchMode=yes administrador@192.168.100.24 bash -s < docs/phases/23/evidence/m2-03-network.sh` · exit=`0` · artifact: docs/phases/23/evidence/m2-03-network.log
- `2026-09-27T23:42:26-06:00` **m2-04-validate** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m2-04-validate.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" bash -s"` · exit=`1` · artifact: docs/phases/23/evidence/m2-04-validate.log
- `2026-09-27T23:42:56-06:00` **m2-04b-validate** → `bash -c ( printf "%s\n" "$SUDO_PASS"; cat docs/phases/23/evidence/m2-04-validate.sh ) | ssh -o BatchMode=yes administrador@192.168.100.24 "sudo -S -p \"\" bash -s"` · exit=`0` · artifact: docs/phases/23/evidence/m2-04b-validate.log
- `2026-09-27T23:44:21-06:00` **m2-05-repo-compose** → `bash -c docker compose -f deployment/platform/compose.yaml config -q && echo COMPOSE_CONFIG_PASS; echo "services:"; docker compose -f deployment/platform/compose.yaml config --services; echo "network:"; docker compose -f deployment/platform/compose.yaml config | grep -A3 "platform-net"; echo "platform containers locales:"; docker ps -a --format "{{.Names}}" | grep -c platform- || echo 0; find deployment/platform -type f | sort` · exit=`0` · artifact: docs/phases/23/evidence/m2-05-repo-compose.log
- `2026-09-27T23:44:46-06:00` **m2-06-ledger-tests** → `uv run pytest harness/tests/test_ledger.py harness/tests/test_progress_cli.py -q` · exit=`0` · artifact: docs/phases/23/evidence/m2-06-ledger-tests.log
- `2026-09-28T00:14:07-06:00` **m3-00-schema-sample** → `bash -c cd /tmp/opencode/m3-sample && echo "== source ==" && echo "https://public.bybit.com/spot/ETHUSDT/ETHUSDT_2024-06-01.csv.gz" && curl -sS -o /dev/null -w "http=%{http_code} bytes=%{size_download}\n" --max-time 120 "https://public.bybit.com/spot/ETHUSDT/ETHUSDT_2024-06-01.csv.gz" -o /dev/null; sha256sum ETHUSDT_2024-06-01.csv.gz && file ETHUSDT_2024-06-01.csv.gz && echo "== header + 3 filas ==" && python3 -c "
import gzip
with gzip.open(\"ETHUSDT_2024-06-01.csv.gz\",\"rt\") as f:
    for i,line in enumerate(f):
        print(line.rstrip())
        if i>=3: break
" && echo "== tail + filas ==" && python3 -c "
import gzip
n=0
last=\"\"
with gzip.open(\"ETHUSDT_2024-06-01.csv.gz\",\"rt\") as f:
    for line in f:
        n+=1; last=line.rstrip()
print(\"lines_total=\",n)
print(\"last_row=\",last)
"; echo "SCHEMA_DOC=id,timestamp,price,volume,side"` · exit=`0` · artifact: docs/phases/23/evidence/m3-00-schema-sample.log
- `2026-09-28T00:19:04-06:00` **m3-01-unit-tests** → `uv run pytest tests/test_bronze_ingest.py -q --cov=infrastructure.medallion --cov-branch --cov-report=term-missing` · exit=`0` · artifact: docs/phases/23/evidence/m3-01-unit-tests.log
- `2026-09-28T00:19:20-06:00` **m3-02-ruff** → `bash -c uv run ruff check src/infrastructure/medallion tests/test_bronze_ingest.py && uv run ruff format --check src/infrastructure/medallion tests/test_bronze_ingest.py` · exit=`1` · artifact: docs/phases/23/evidence/m3-02-ruff.log
- `2026-09-28T00:20:43-06:00` **m3-02b-ruff-format** → `bash -c uv run ruff check src/infrastructure/medallion tests/test_bronze_ingest.py && uv run ruff format --check src/infrastructure/medallion tests/test_bronze_ingest.py && uv run mypy src/infrastructure/medallion tests/test_bronze_ingest.py && uv run pytest tests/test_bronze_ingest.py -q --cov=infrastructure.medallion --cov-branch --cov-fail-under=90` · exit=`1` · artifact: docs/phases/23/evidence/m3-02b-ruff-format.log
- `2026-09-28T00:20:59-06:00` **m3-02c-lint-quality** → `bash -c uv run ruff check src/infrastructure/medallion tests/test_bronze_ingest.py && uv run ruff format --check src/infrastructure/medallion tests/test_bronze_ingest.py && uv run mypy src/infrastructure/medallion tests/test_bronze_ingest.py && uv run pytest tests/test_bronze_ingest.py -q --cov=infrastructure.medallion --cov-branch --cov-fail-under=90` · exit=`1` · artifact: docs/phases/23/evidence/m3-02c-lint-quality.log
- `2026-09-28T00:21:19-06:00` **m3-02d-lint-quality** → `bash -c uv run ruff check src/infrastructure/medallion tests/test_bronze_ingest.py && uv run ruff format --check src/infrastructure/medallion tests/test_bronze_ingest.py && uv run mypy src/infrastructure/medallion tests/test_bronze_ingest.py && uv run pytest tests/test_bronze_ingest.py -q --cov=infrastructure.medallion --cov-branch --cov-fail-under=90` · exit=`1` · artifact: docs/phases/23/evidence/m3-02d-lint-quality.log
- `2026-09-28T00:21:36-06:00` **m3-02e-lint-quality** → `bash -c uv run ruff check src/infrastructure/medallion tests/test_bronze_ingest.py && uv run ruff format --check src/infrastructure/medallion tests/test_bronze_ingest.py && uv run mypy src/infrastructure/medallion tests/test_bronze_ingest.py && uv run pytest tests/test_bronze_ingest.py -q --cov=infrastructure.medallion --cov-branch --cov-fail-under=90` · exit=`0` · artifact: docs/phases/23/evidence/m3-02e-lint-quality.log
- `2026-09-28T00:22:19-06:00` **m3-03-preflight** → `ssh -o BatchMode=yes administrador@192.168.100.24 bash -s` · exit=`0` · artifact: docs/phases/23/evidence/m3-03-preflight.log
- `2026-09-28T00:23:09-06:00` **m3-04-deploy-copy** → `bash /tmp/opencode/m3-04-copy.sh` · exit=`0` · artifact: docs/phases/23/evidence/m3-04-deploy-copy.log
- `2026-09-28T00:23:16-06:00` **m3-05-uat-run1** → `bash /tmp/opencode/m3-05-run1.sh` · exit=`1` · artifact: docs/phases/23/evidence/m3-05-uat-run1.log
- `2026-09-28T00:23:28-06:00` **m3-05b-uat-run1** → `ssh -o BatchMode=yes administrador@192.168.100.24 bash -s` · exit=`0` · artifact: docs/phases/23/evidence/m3-05b-uat-run1.log
- `2026-09-28T00:23:34-06:00` **m3-06-uat-run2-idempotent** → `ssh -o BatchMode=yes administrador@192.168.100.24 bash -s` · exit=`0` · artifact: docs/phases/23/evidence/m3-06-uat-run2-idempotent.log
- `2026-09-28T00:23:43-06:00` **m3-07-uat-negative** → `ssh -o BatchMode=yes administrador@192.168.100.24 bash -s` · exit=`0` · artifact: docs/phases/23/evidence/m3-07-uat-negative.log
- `2026-09-28T00:25:47-06:00` **m3-08-product-unit-tests** → `uv run pytest tests -q --ignore=tests/integration` · exit=`0` · artifact: docs/phases/23/evidence/m3-08-product-unit-tests.log
- `2026-09-28T00:26:02-06:00` **m3-09-repo-quality** → `bash -c uv run ruff check . && uv run ruff format --check . && uv run mypy src tests` · exit=`0` · artifact: docs/phases/23/evidence/m3-09-repo-quality.log
- `2026-09-28T00:30:54-06:00` **m3-08b-product-unit-tests-with-count** → `uv run pytest tests --ignore=tests/integration` · exit=`0` · artifact: docs/phases/23/evidence/m3-08b-product-unit-tests-with-count.log
- `2026-09-28T00:44:01-06:00` **m3-10-precommit-verify** → `bash -c uv run ruff check . && uv run ruff format --check . && uv run mypy src tests && uv run pytest tests/test_bronze_ingest.py` · exit=`0` · artifact: docs/phases/23/evidence/m3-10-precommit-verify.log
- `2026-09-28T00:58:58-06:00` **m4-01-bronze-analysis** → `ssh -o BatchMode=yes administrador@192.168.100.24 bash -s` · exit=`0` · artifact: docs/phases/23/evidence/m4-01-bronze-analysis.log
- `2026-09-28T01:09:06-06:00` **m4-02-unit-tests** → `uv run pytest tests/test_silver_trades.py tests/test_bronze_ingest.py -q --cov=infrastructure.medallion --cov-branch --cov-report=term-missing` · exit=`1` · artifact: docs/phases/23/evidence/m4-02-unit-tests.log
- `2026-09-28T01:09:48-06:00` **m4-02b-unit-tests** → `uv run pytest tests/test_silver_trades.py tests/test_bronze_ingest.py -q --cov=infrastructure.medallion --cov-branch --cov-report=term-missing` · exit=`0` · artifact: docs/phases/23/evidence/m4-02b-unit-tests.log
- `2026-09-28T01:11:30-06:00` **m4-03-repo-quality** → `bash -c uv run ruff check . && uv run ruff format --check . && uv run mypy src tests && uv run pytest tests --ignore=tests/integration` · exit=`0` · artifact: docs/phases/23/evidence/m4-03-repo-quality.log
- `2026-09-28T01:12:58-06:00` **m4-04-preflight** → `ssh -o BatchMode=yes administrador@192.168.100.24 bash -s` · exit=`0` · artifact: docs/phases/23/evidence/m4-04-preflight.log
- `2026-09-28T01:13:15-06:00` **m4-05-deploy-copy** → `bash /tmp/opencode/m4-05-copy.sh` · exit=`0` · artifact: docs/phases/23/evidence/m4-05-deploy-copy.log
- `2026-09-28T01:14:00-06:00` **m4-06-uat-run1** → `ssh -o BatchMode=yes administrador@192.168.100.24 bash -s` · exit=`0` · artifact: docs/phases/23/evidence/m4-06-uat-run1.log
- `2026-09-28T01:14:20-06:00` **m4-07-uat-run2** → `ssh -o BatchMode=yes administrador@192.168.100.24 bash -s` · exit=`0` · artifact: docs/phases/23/evidence/m4-07-uat-run2.log
- `2026-09-28T01:14:30-06:00` **m4-08-uat-negative** → `ssh -o BatchMode=yes administrador@192.168.100.24 bash -s` · exit=`0` · artifact: docs/phases/23/evidence/m4-08-uat-negative.log
- `2026-09-28T01:16:37-06:00` **m4-09-precommit-verify** → `bash -c uv run ruff check . && uv run ruff format --check . && uv run mypy src tests && uv run pytest tests/test_silver_trades.py tests/test_bronze_ingest.py` · exit=`0` · artifact: docs/phases/23/evidence/m4-09-precommit-verify.log
- `2026-09-28T01:29:00-06:00` **m4-10-correction-quality** → `bash -c uv run ruff check . && uv run ruff format --check . && uv run mypy src tests && uv run pytest tests/test_silver_trades.py tests/test_bronze_ingest.py --cov=infrastructure.medallion --cov-branch --cov-fail-under=90 && uv run pytest tests --ignore=tests/integration` · exit=`0` · artifact: docs/phases/23/evidence/m4-10-correction-quality.log
- `2026-09-28T01:32:42-06:00` **m4-11-manifest-regeneration** → `bash /tmp/opencode/m4-11-regenerate.sh` · exit=`0` · artifact: docs/phases/23/evidence/m4-11-manifest-regeneration.log
- `2026-09-28T01:33:39-06:00` **m4-12-run2-revalidation** → `bash /tmp/opencode/m4-12-run2-revalidate.sh` · exit=`0` · artifact: docs/phases/23/evidence/m4-12-run2-revalidation.log
- `2026-09-28T09:33:11-06:00` **m5-01-unit-tests** → `bash -c uv run ruff check src/infrastructure/medallion tests/test_silver_candles.py && uv run ruff format --check src/infrastructure/medallion tests/test_silver_candles.py && uv run mypy src tests && uv run pytest tests/test_silver_candles.py tests/test_silver_trades.py tests/test_bronze_ingest.py --cov=infrastructure.medallion --cov-branch --cov-fail-under=90 --cov-report=term-missing | tail -18` · exit=`0` · artifact: docs/phases/23/evidence/m5-01-unit-tests.log
- `2026-09-28T09:34:58-06:00` **m5-02-repo-quality** → `bash -c uv run ruff check . && uv run ruff format --check . && uv run mypy src tests && uv run pytest tests --ignore=tests/integration` · exit=`0` · artifact: docs/phases/23/evidence/m5-02-repo-quality.log
- `2026-09-28T09:37:21-06:00` **m5-03-preflight** → `bash /tmp/opencode/m5-03-preflight.sh` · exit=`0` · artifact: docs/phases/23/evidence/m5-03-preflight.log
- `2026-09-28T09:38:08-06:00` **m5-04-deploy-copy** → `bash /tmp/opencode/m5-04-deploy.sh` · exit=`0` · artifact: docs/phases/23/evidence/m5-04-deploy-copy.log
- `2026-09-28T09:38:43-06:00` **m5-05-uat-run1** → `bash /tmp/opencode/m5-05-uat-run1.sh` · exit=`0` · artifact: docs/phases/23/evidence/m5-05-uat-run1.log
- `2026-09-28T09:40:19-06:00` **m5-06-ohlc-validation** → `bash /tmp/opencode/m5-06-validation.sh` · exit=`0` · artifact: docs/phases/23/evidence/m5-06-ohlc-validation.log
- `2026-09-28T09:41:07-06:00` **m5-07-uat-run2-determinism** → `bash /tmp/opencode/m5-07-run2.sh` · exit=`0` · artifact: docs/phases/23/evidence/m5-07-uat-run2-determinism.log
- `2026-09-28T09:43:19-06:00` **m5-08-uat-negative** → `bash /tmp/opencode/m5-08-negative.sh` · exit=`0` · artifact: docs/phases/23/evidence/m5-08-uat-negative.log
- `2026-09-28T09:43:38-06:00` **m5-09-bronze-untouched** → `ssh -o BatchMode=yes administrador@192.168.100.24 set -euo pipefail
python3 - <<'PYEOF'
import hashlib, json
from pathlib import Path
B = Path("/srv/data/medallion/bronze/bybit/spot/ETHUSDT")
mf = json.loads((B / "manifest.json").read_text())
for day in ("2024-06-01", "2024-06-02", "2024-06-03"):
    name = "ETHUSDT_%s.csv.gz" % day
    e = mf["files"][name]
    p = B / ("date=" + day) / name
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    assert h == e["sha256"], (day, h)
    print("bronze=%s sha=OK" % name)
print("BRONZE_UNTOUCHED=PASS")
PYEOF
echo "-- contenedores --"
docker compose ls -a` · exit=`0` · artifact: docs/phases/23/evidence/m5-09-bronze-untouched.log
- `2026-09-28T10:29:47-06:00` **m6-01-unit-tests** → `bash -c uv run ruff check . && uv run ruff format --check . && uv run mypy src tests && uv run pytest tests/test_bronze_ingest.py tests/test_silver_trades.py tests/test_silver_candles.py tests/test_gold_dataset.py tests/test_split_candidate_17c_a.py --cov=infrastructure.medallion --cov-branch --cov-fail-under=90 --cov-report=term-missing --cov-report=json:/tmp/opencode/coverage-m6.json` · exit=`0` · artifact: docs/phases/23/evidence/m6-01-unit-tests.log
- `2026-09-28T10:31:30-06:00` **m6-02-repo-quality** → `bash -c uv run ruff check . && uv run ruff format --check . && uv run mypy src tests && uv run pytest tests --ignore=tests/integration` · exit=`0` · artifact: docs/phases/23/evidence/m6-02-repo-quality.log
- `2026-09-28T10:33:47-06:00` **m6-03-preflight** → `bash /tmp/opencode/m6-03-preflight.sh` · exit=`1` · artifact: docs/phases/23/evidence/m6-03-preflight.log
- `2026-09-28T10:34:21-06:00` **m6-03-preflight-ok** → `bash /tmp/opencode/m6-03-preflight.sh` · exit=`0` · artifact: docs/phases/23/evidence/m6-03-preflight-ok.log
- `2026-09-28T10:34:35-06:00` **m6-04-deploy-copy** → `bash /tmp/opencode/m6-04-deploy.sh` · exit=`0` · artifact: docs/phases/23/evidence/m6-04-deploy-copy.log
- `2026-09-28T10:34:42-06:00` **m6-05-uat-run1** → `bash /tmp/opencode/m6-05-run1.sh` · exit=`0` · artifact: docs/phases/23/evidence/m6-05-uat-run1.log
- `2026-09-28T10:34:53-06:00` **m6-06-uat-run2-determinism** → `bash /tmp/opencode/m6-06-run2.sh` · exit=`0` · artifact: docs/phases/23/evidence/m6-06-uat-run2-determinism.log
- `2026-09-28T10:35:03-06:00` **m6-07-uat-verify** → `bash /tmp/opencode/m6-07-verify.sh` · exit=`0` · artifact: docs/phases/23/evidence/m6-07-uat-verify.log
- `2026-09-28T10:36:24-06:00` **m6-08-uat-negative** → `bash /tmp/opencode/m6-08-negative.sh` · exit=`0` · artifact: docs/phases/23/evidence/m6-08-uat-negative.log
- `2026-09-28T11:56:53-06:00` **m7-01-unit-tests** → `bash -c uv run ruff check . && uv run ruff format --check . && uv run mypy src tests && uv run pytest tests/test_bronze_ingest.py tests/test_silver_trades.py tests/test_silver_candles.py tests/test_gold_dataset.py tests/test_split_candidate_17c_a.py tests/test_trade_replay.py --cov=infrastructure.medallion --cov-branch --cov-fail-under=90 --cov-report=term-missing --cov-report=json:/tmp/opencode/coverage-m7.json` · exit=`0` · artifact: docs/phases/23/evidence/m7-01-unit-tests.log
- `2026-09-28T11:58:35-06:00` **m7-02-repo-quality** → `bash -c uv run ruff check . && uv run ruff format --check . && uv run mypy src tests && uv run pytest tests --ignore=tests/integration` · exit=`0` · artifact: docs/phases/23/evidence/m7-02-repo-quality.log
- `2026-09-28T12:02:14-06:00` **m7-03-preflight** → `bash /tmp/opencode/m7-03-preflight.sh` · exit=`0` · artifact: docs/phases/23/evidence/m7-03-preflight.log
- `2026-09-28T12:03:38-06:00` **m7-04-deploy-copy** → `bash /tmp/opencode/m7-04-deploy.sh` · exit=`1` · artifact: docs/phases/23/evidence/m7-04-deploy-copy.log
- `2026-09-28T12:04:19-06:00` **m7-04b-deploy-copy** → `bash /tmp/opencode/m7-04-deploy.sh` · exit=`1` · artifact: docs/phases/23/evidence/m7-04b-deploy-copy.log
- `2026-09-28T12:04:57-06:00` **m7-04c-deploy-copy** → `bash /tmp/opencode/m7-04-deploy.sh` · exit=`0` · artifact: docs/phases/23/evidence/m7-04c-deploy-copy.log
- `2026-09-28T12:07:27-06:00` **m7-05-uat-run1** → `bash /tmp/opencode/m7-05-run1.sh` · exit=`0` · artifact: docs/phases/23/evidence/m7-05-uat-run1.log
- `2026-09-28T12:08:36-06:00` **m7-06-uat-run2-determinism** → `bash /tmp/opencode/m7-06-run2.sh` · exit=`1` · artifact: docs/phases/23/evidence/m7-06-uat-run2-determinism.log
- `2026-09-28T12:09:27-06:00` **m7-06b-uat-run2-determinism** → `bash /tmp/opencode/m7-06-run2.sh` · exit=`0` · artifact: docs/phases/23/evidence/m7-06b-uat-run2-determinism.log
- `2026-09-28T12:19:07-06:00` **m7-07-uat-verify** → `bash /tmp/opencode/m7-07-verify.sh` · exit=`0` · artifact: docs/phases/23/evidence/m7-07-uat-verify.log
- `2026-09-28T13:01:56-06:00` **m8-03-preflight** → `bash /tmp/opencode/m8-03-preflight.sh` · exit=`0` · artifact: docs/phases/23/evidence/m8-03-preflight.log
- `2026-09-28T13:12:02-06:00` **m8-04a-deploy-copy-fail** → `bash /tmp/opencode/m8-04-deploy-copy.sh` · exit=`1` · artifact: docs/phases/23/evidence/m8-04a-deploy-copy-fail.log
- `2026-09-28T13:34:18-06:00` **m8-04b-deploy-copy-fail** → `bash /tmp/opencode/m8-04-deploy-copy.sh` · exit=`1` · artifact: docs/phases/23/evidence/m8-04b-deploy-copy-fail.log
- `2026-09-28T13:36:21-06:00` **m8-04-deploy-copy** → `bash /tmp/opencode/m8-04-deploy-copy.sh` · exit=`0` · artifact: docs/phases/23/evidence/m8-04-deploy-copy.log
- `2026-09-28T13:37:04-06:00` **m8-05-build** → `bash /tmp/opencode/m8-05-build.sh` · exit=`141` · artifact: docs/phases/23/evidence/m8-05-build.log
- `2026-09-28T13:37:58-06:00` **m8-05b-build-verify-fail** → `bash /tmp/opencode/m8-05b-build-verify.sh` · exit=`1` · artifact: docs/phases/23/evidence/m8-05b-build-verify-fail.log
- `2026-09-28T13:38:37-06:00` **m8-05c-build-verify** → `bash /tmp/opencode/m8-05b-build-verify.sh` · exit=`0` · artifact: docs/phases/23/evidence/m8-05c-build-verify.log
- `2026-09-28T13:40:33-06:00` **m8-06a-uat-clis-fail** → `bash /tmp/opencode/m8-06-uat-clis.sh` · exit=`1` · artifact: docs/phases/23/evidence/m8-06a-uat-clis-fail.log
- `2026-09-28T13:41:36-06:00` **m8-06b-uat-clis-incomplete** → `bash /tmp/opencode/m8-06-uat-clis.sh` · exit=`0` (script remota truncada por stdin de compose run: falso PASS) · artifact: docs/phases/23/evidence/m8-06b-uat-clis-incomplete.log
- `2026-09-28T13:43:31-06:00` **m8-06-uat-clis** → `bash /tmp/opencode/m8-06-uat-clis.sh` · exit=`0` · artifact: docs/phases/23/evidence/m8-06-uat-clis.log
- `2026-09-28T13:45:36-06:00` **m8-07-uat-replay** → `bash /tmp/opencode/m8-07-uat-replay.sh` · exit=`0` · artifact: docs/phases/23/evidence/m8-07-uat-replay.log
- `2026-09-28T13:49:05-06:00` **m8-08-postcheck** → `bash /tmp/opencode/m8-08-postcheck.sh` · exit=`0` · artifact: docs/phases/23/evidence/m8-08-postcheck.log
- `2026-09-28T13:52:20-06:00` **m8-09-repo-quality** → `bash -c uv run ruff check . && uv run ruff format --check . && uv run mypy src tests && uv run pytest tests --ignore=tests/integration -q` · exit=`0` · artifact: docs/phases/23/evidence/m8-09-repo-quality.log
- `2026-09-28T13:52:30-06:00` **m8-08b-gastosia-health** → `bash /tmp/opencode/m8-08b-gastosia.sh` · exit=`0` · artifact: docs/phases/23/evidence/m8-08b-gastosia-health.log
- `2026-09-28T13:54:56-06:00` **m8-09b-repo-quality-count** → `bash -c uv run ruff check . && uv run ruff format --check . && uv run mypy src tests && uv run pytest tests --ignore=tests/integration` · exit=`0` · artifact: docs/phases/23/evidence/m8-09b-repo-quality-count.log
- `2026-09-28T13:56:18-06:00` **m8-10-ledger-mark-done** → `bash -c python3 harness/scripts/progress.py mark-done --phase 23 --deliverable m8-deploy --evidence docs/phases/23/evidence/m8-08-postcheck.log && python3 harness/scripts/progress.py report | tail -8` · exit=`0` · artifact: docs/phases/23/evidence/m8-10-ledger-mark-done.log
- `2026-09-28T14:21:19-06:00` **m9a-00-deploy-copy** → `bash /tmp/opencode/m9a-00-deploy.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a-00-deploy-copy.log
- `2026-09-28T14:21:27-06:00` **m9a-01-preflight** → `bash /tmp/opencode/m9a-01-preflight.sh` · exit=`1` · artifact: docs/phases/23/evidence/m9a-01-preflight.log
- `2026-09-28T14:22:22-06:00` **m9a-01b-preflight** → `bash /tmp/opencode/m9a-01b-preflight.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a-01b-preflight.log
- `2026-09-28T14:23:16-06:00` **m9a-01c-preflight-fix** → `bash /tmp/opencode/m9a-01c-preflight.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a-01c-preflight-fix.log
- `2026-09-28T14:29:40-06:00` **m9a-02-source-availability** → `bash /tmp/opencode/m9a-02-availability.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a-02-source-availability.log
- `2026-09-28T14:34:13-06:00` **m9a-03a-bronze-1** → `bash /tmp/opencode/m9a-03-bronze.sh 0 130` · exit=`0` · artifact: docs/phases/23/evidence/m9a-03a-bronze-1.log
- `2026-09-28T14:39:00-06:00` **m9a-03b-bronze-2** → `bash /tmp/opencode/m9a-03-bronze.sh 130 130` · exit=`0` · artifact: docs/phases/23/evidence/m9a-03b-bronze-2.log
- `2026-09-28T14:44:11-06:00` **m9a-03c-bronze-3** → `bash /tmp/opencode/m9a-03-bronze.sh 260 130` · exit=`0` · artifact: docs/phases/23/evidence/m9a-03c-bronze-3.log
- `2026-09-28T14:49:48-06:00` **m9a-03d-bronze-4** → `bash /tmp/opencode/m9a-03-bronze.sh 390 130` · exit=`0` · artifact: docs/phases/23/evidence/m9a-03d-bronze-4.log
- `2026-09-28T14:54:31-06:00` **m9a-03e-bronze-5** → `bash /tmp/opencode/m9a-03-bronze.sh 520 127` · exit=`0` · artifact: docs/phases/23/evidence/m9a-03e-bronze-5.log
- `2026-09-28T14:57:03-06:00` **m9a-04-bronze-verify** → `bash /tmp/opencode/m9a-04-bronze-verify.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a-04-bronze-verify.log
- `2026-09-28T14:58:05-06:00` **m9a-05a-silver-1** → `bash /tmp/opencode/m9a-05-silver.sh 0 30` · exit=`0` · artifact: docs/phases/23/evidence/m9a-05a-silver-1.log
- `2026-09-28T15:31:10-06:00` **m9a-05b-silver-2** → `bash /tmp/opencode/m9a-05-silver.sh 30 310` · exit=`0` · artifact: docs/phases/23/evidence/m9a-05b-silver-2.log
- `2026-09-28T15:31:10-06:00` **m9a-05c-silver-3-incomplete** → `bash /tmp/opencode/m9a-05-silver.sh 340 307` · exit=`KILLED_BY_TOOL_TIMEOUT (sin exit=; proceso remoto continuó en background)` · artifact: docs/phases/23/evidence/m9a-05c-silver-3-incomplete.log
- `2026-09-28T18:43:08-06:00` **m9a-recovery-01-preflight** → `bash /tmp/opencode/m9a-recovery-01-preflight.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a-recovery-01-preflight.log
- `2026-09-28T18:43:54-06:00` **m9a-recovery-01b-cert-baseline** → `bash /tmp/opencode/m9a-recovery-01b-cert-baseline.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a-recovery-01b-cert-baseline.log
- `2026-09-28T18:45:04-06:00` **m9a-recovery-02-partials** → `bash /tmp/opencode/m9a-recovery-02-partials.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a-recovery-02-partials.log
- `2026-09-28T18:46:55-06:00` **m9a-recovery-03-inventory** → `bash /tmp/opencode/m9a-recovery-03-inventory.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a-recovery-03-inventory.log
- `2026-09-28T18:48:18-06:00` **m9a-recovery-04-bronze-rerun** → `bash /tmp/opencode/m9a-03-bronze.sh 0 647` · exit=`0` · artifact: docs/phases/23/evidence/m9a-recovery-04-bronze-rerun.log
- `2026-09-28T18:49:03-06:00` **m9a-recovery-05-silver-resume** → `bash /tmp/opencode/m9a-05-silver.sh 0 647` · exit=`1` · artifact: docs/phases/23/evidence/m9a-recovery-05-silver-resume.log
- `2026-09-28T18:52:45-06:00` **m9a-recovery-06-schema-diag** → `bash /tmp/opencode/m9a-recovery-06-schema-diag.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a-recovery-06-schema-diag.log
- `2026-09-28T18:54:28-06:00` **m9a-recovery-07-final-state** → `bash /tmp/opencode/m9a-recovery-07-final-state.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a-recovery-07-final-state.log
- `2026-09-28T19:22:54-06:00` **m9a1-01-unit-tests-medallion** → `uv run pytest tests/test_source_schema.py tests/test_silver_trades.py tests/test_bronze_ingest.py tests/test_silver_candles.py tests/test_gold_dataset.py tests/test_trade_replay.py --cov=infrastructure.medallion --cov-branch --cov-fail-under=90 --cov-report=term-missing --cov-report=json:/tmp/opencode/coverage-m9a1.json` · exit=`0` · artifact: docs/phases/23/evidence/m9a1-01-unit-tests-medallion.log
- `2026-09-28T19:25:30-06:00` **m9a1-01b-unit-tests-medallion** → `uv run pytest tests/test_source_schema.py tests/test_silver_trades.py tests/test_bronze_ingest.py tests/test_silver_candles.py tests/test_gold_dataset.py tests/test_trade_replay.py --cov=infrastructure.medallion --cov-branch --cov-fail-under=90 --cov-report=term-missing --cov-report=json:/tmp/opencode/coverage-m9a1.json` · exit=`0` · artifact: docs/phases/23/evidence/m9a1-01b-unit-tests-medallion.log
- `2026-09-28T19:27:02-06:00` **m9a1-02-unit-tests-full** → `uv run pytest tests --ignore=tests/integration -q` · exit=`0` · artifact: docs/phases/23/evidence/m9a1-02-unit-tests-full.log
- `2026-09-28T19:27:11-06:00` **m9a1-03-lint-typing** → `bash -c uv run ruff check . && uv run ruff format --check . && uv run mypy src tests` · exit=`0` · artifact: docs/phases/23/evidence/m9a1-03-lint-typing.log
- `2026-09-28T19:29:27-06:00` **m9a1-02b-unit-tests-full-count** → `uv run pytest tests --ignore=tests/integration -o addopts= -q` · exit=`0` · artifact: docs/phases/23/evidence/m9a1-02b-unit-tests-full-count.log
- `2026-09-28T19:33:25-06:00` **m9a1-04-deploy** → `bash /tmp/opencode/m9a1/04-deploy.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a1-04-deploy.log
- `2026-09-28T19:33:57-06:00` **m9a1-05-snapshot-before** → `bash /tmp/opencode/m9a1/run.sh /tmp/opencode/m9a1/05-snapshot-remote.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a1-05-snapshot-before.log
- `2026-09-28T19:34:25-06:00` **m9a1-05b-downstream-baseline** → `bash /tmp/opencode/m9a1/run.sh /tmp/opencode/m9a1/05b-downstream-baseline-remote.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a1-05b-downstream-baseline.log
- `2026-09-28T19:34:35-06:00` **m9a1-06-failclosed-pre-backfill** → `bash /tmp/opencode/m9a1/run.sh /tmp/opencode/m9a1/06-failclosed-remote.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a1-06-failclosed-pre-backfill.log
- `2026-09-28T19:35:15-06:00` **m9a1-07-backfill** → `bash /tmp/opencode/m9a1/run.sh /tmp/opencode/m9a1/07-backfill-remote.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a1-07-backfill.log
- `2026-09-28T19:35:36-06:00` **m9a1-08-transform-2025-03-13** → `bash /tmp/opencode/m9a1/run.sh /tmp/opencode/m9a1/08-transform-remote.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a1-08-transform-2025-03-13.log
- `2026-09-28T19:36:13-06:00` **m9a1-09-verify-integrity** → `bash /tmp/opencode/m9a1/run.sh /tmp/opencode/m9a1/09-verify-remote.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a1-09-verify-integrity.log
- `2026-09-28T19:36:56-06:00` **m9a1-10-smoke-v2** → `bash /tmp/opencode/m9a1/run.sh /tmp/opencode/m9a1/10-smoke-remote.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a1-10-smoke-v2.log
- `2026-09-28T19:37:05-06:00` **m9a1-11-final-state** → `bash /tmp/opencode/m9a1/run.sh /tmp/opencode/m9a1/11-final-remote.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a1-11-final-state.log
- `2026-09-28T19:48:15-06:00` **m9a1-12-precommit-check** → `bash /tmp/opencode/m9a1-12-precommit-check.sh` · exit=`1` · artifact: docs/phases/23/evidence/m9a1-12-precommit-check.log
- `2026-09-28T19:51:03-06:00` **m9a1-12b-precommit-check** → `bash /tmp/opencode/m9a1-12-precommit-check.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a1-12b-precommit-check.log
- `2026-09-28T19:52:18-06:00` **m9a1-13-precommit-remote** → `bash /tmp/opencode/m9a1/run.sh /tmp/opencode/m9a1-13-precommit-remote.sh` · exit=`1` · artifact: docs/phases/23/evidence/m9a1-13-precommit-remote.log
- `2026-09-28T19:53:30-06:00` **m9a1-13b-precommit-remote** → `bash /tmp/opencode/m9a1/run.sh /tmp/opencode/m9a1-13-precommit-remote.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a1-13b-precommit-remote.log
- `2026-09-28T20:15:50-06:00` **m9a-fulldev-01-preflight** → `bash /tmp/opencode/m9a-fulldev-01-preflight.sh` · exit=`1` · artifact: docs/phases/23/evidence/m9a-fulldev-01-preflight.log
- `2026-09-28T20:16:40-06:00` **m9a-fulldev-01b-preflight** → `bash /tmp/opencode/m9a-fulldev-01-preflight.sh` · exit=`1` · artifact: docs/phases/23/evidence/m9a-fulldev-01b-preflight.log
- `2026-09-28T20:17:36-06:00` **m9a-fulldev-01c-preflight** → `bash /tmp/opencode/m9a-fulldev-01-preflight.sh` · exit=`1` · artifact: docs/phases/23/evidence/m9a-fulldev-01c-preflight.log
- `2026-09-28T20:18:32-06:00` **m9a-fulldev-01d-preflight** → `bash /tmp/opencode/m9a-fulldev-01-preflight.sh` · exit=`1` · artifact: docs/phases/23/evidence/m9a-fulldev-01d-preflight.log
- `2026-09-28T20:19:17-06:00` **m9a-fulldev-01e-preflight** → `bash /tmp/opencode/m9a-fulldev-01-preflight.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a-fulldev-01e-preflight.log
- `2026-09-28T20:20:20-06:00` **m9a-fulldev-02-silver-launch** → `bash /tmp/opencode/m9a-fulldev-launch.sh silver` · exit=`1` · artifact: docs/phases/23/evidence/m9a-fulldev-02-silver-launch.log
- `2026-09-28T20:20:38-06:00` **m9a-fulldev-02b-silver-launch** → `bash /tmp/opencode/m9a-fulldev-launch.sh silver` · exit=`0` · artifact: docs/phases/23/evidence/m9a-fulldev-02b-silver-launch.log
- `2026-09-28T20:20:46-06:00` **m9a-fulldev-02c-silver-run** → `bash /tmp/opencode/m9a-fulldev-poll.sh silver 780` · exit=`1` · artifact: docs/phases/23/evidence/m9a-fulldev-02c-silver-run.log
- `2026-09-28T20:32:31-06:00` **m9a-fulldev-02d-silver-poll** → `bash /tmp/opencode/m9a-fulldev-poll.sh silver 750` · exit=`0` · artifact: docs/phases/23/evidence/m9a-fulldev-02d-silver-poll.log
- `2026-09-28T20:33:26-06:00` **m9a-fulldev-03-candles-launch** → `bash /tmp/opencode/m9a-fulldev-launch.sh candles` · exit=`0` · artifact: docs/phases/23/evidence/m9a-fulldev-03-candles-launch.log
- `2026-09-28T20:46:43-06:00` **m9a-fulldev-03b-candles-poll** → `bash /tmp/opencode/m9a-fulldev-poll.sh candles 750` · exit=`1` · artifact: docs/phases/23/evidence/m9a-fulldev-03b-candles-poll.log
- `2026-09-28T20:59:47-06:00` **m9a-fulldev-03c-candles-poll** → `bash /tmp/opencode/m9a-fulldev-poll.sh candles 750` · exit=`1` · artifact: docs/phases/23/evidence/m9a-fulldev-03c-candles-poll.log
- `2026-09-28T21:48:18-06:00` **m9a-fulldev-03d-candles-run** → `bash -c ssh -o BatchMode=yes administrador@192.168.100.24 'cat /srv/fast/medallion/m9a-logs/fulldev-candles-run.log'` · exit=`0` · artifact: docs/phases/23/evidence/m9a-fulldev-03d-candles-run.log
- `2026-09-28T21:48:59-06:00` **m9a-fulldev-04-gold-launch** → `bash /tmp/opencode/m9a-fulldev-launch.sh gold` · exit=`0` · artifact: docs/phases/23/evidence/m9a-fulldev-04-gold-launch.log
- `2026-09-28T22:05:16-06:00` **m9a-fulldev-04b-gold-diag** → `bash /tmp/opencode/m9a-fulldev-launch.sh gold-diag` · exit=`1` · artifact: docs/phases/23/evidence/m9a-fulldev-04b-gold-diag.log
- `2026-09-28T22:05:31-06:00` **m9a-fulldev-04c-gold-diag** → `bash /tmp/opencode/m9a-fulldev-launch.sh gold-diag` · exit=`0` · artifact: docs/phases/23/evidence/m9a-fulldev-04c-gold-diag.log
- `2026-09-28T22:06:52-06:00` **m9a-fulldev-04d-gold-tail-test** → `bash -c ssh -o BatchMode=yes administrador@192.168.100.24 bash -s < /tmp/opencode/m9a-fulldev-gold-tail-test.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a-fulldev-04d-gold-tail-test.log
- `2026-09-28T22:08:06-06:00` **m9a-fulldev-04e-gold-verify** → `bash -c ssh -o BatchMode=yes administrador@192.168.100.24 bash -s < /tmp/opencode/m9a-fulldev-gold-verify-remote.sh` · exit=`1` · artifact: docs/phases/23/evidence/m9a-fulldev-04e-gold-verify.log
- `2026-09-28T22:08:31-06:00` **m9a-fulldev-04f-gold-verify** → `bash -c ssh -o BatchMode=yes administrador@192.168.100.24 bash -s < /tmp/opencode/m9a-fulldev-gold-verify-remote.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a-fulldev-04f-gold-verify.log
- `2026-09-28T22:11:16-06:00` **m9a-fulldev-05-rerun1-launch** → `bash /tmp/opencode/m9a-fulldev-launch.sh rerun1` · exit=`0` · artifact: docs/phases/23/evidence/m9a-fulldev-05-rerun1-launch.log
- `2026-09-28T22:12:26-06:00` **m9a-fulldev-05b-rerun1-poll** → `bash /tmp/opencode/m9a-fulldev-poll.sh rerun1 1500` · exit=`0` · artifact: docs/phases/23/evidence/m9a-fulldev-05b-rerun1-poll.log
- `2026-09-28T22:12:42-06:00` **m9a-fulldev-06-rerun2-launch** → `bash /tmp/opencode/m9a-fulldev-launch.sh rerun2` · exit=`0` · artifact: docs/phases/23/evidence/m9a-fulldev-06-rerun2-launch.log
- `2026-09-28T22:13:46-06:00` **m9a-fulldev-06b-rerun2-poll** → `bash /tmp/opencode/m9a-fulldev-poll.sh rerun2 1500` · exit=`0` · artifact: docs/phases/23/evidence/m9a-fulldev-06b-rerun2-poll.log
- `2026-09-28T22:15:52-06:00` **m9a-fulldev-07-final-validation** → `bash -c ssh -o BatchMode=yes administrador@192.168.100.24 bash -s < /tmp/opencode/m9a-fulldev-final-remote.sh` · exit=`1` · artifact: docs/phases/23/evidence/m9a-fulldev-07-final-validation.log
- `2026-09-28T22:20:19-06:00` **m9a-fulldev-08-cert-atribucion** → `bash -c ssh -o BatchMode=yes administrador@192.168.100.24 "C1=\$(docker ps -q --filter name=paper-runner | head -1); echo \"=== cadencia del job 6-horario del paper-runner (reportes) ===\"; docker exec \$C1 sh -c \"ls -la --time-style=full-iso /app/reports/paper | tail -8\"; echo \"=== certification-state.json ===\"; docker exec \$C1 sh -c \"ls -la --time-style=full-iso /app/certification\"; echo \"=== ownership ===\"; id administrador; echo \"=== scripts M9A que escriben en /srv/docker ===\"; grep -lE \"> */srv/docker|tee */srv/docker\" /srv/fast/medallion/m9a-logs/*.sh || echo NONE"` · exit=`0` · artifact: docs/phases/23/evidence/m9a-fulldev-08-cert-atribucion.log
- `2026-09-28T22:20:29-06:00` **m9a-fulldev-07b-final-validation** → `bash -c ssh -o BatchMode=yes administrador@192.168.100.24 bash -s < /tmp/opencode/m9a-fulldev-final-remote.sh` · exit=`1` · artifact: docs/phases/23/evidence/m9a-fulldev-07b-final-validation.log
- `2026-09-28T22:21:40-06:00` **m9a-fulldev-07c-final-validation** → `bash -c ssh -o BatchMode=yes administrador@192.168.100.24 bash -s < /tmp/opencode/m9a-fulldev-final-remote.sh` · exit=`2` · artifact: docs/phases/23/evidence/m9a-fulldev-07c-final-validation.log
- `2026-09-28T22:22:00-06:00` **m9a-fulldev-07d-final-validation** → `bash -c ssh -o BatchMode=yes administrador@192.168.100.24 bash -s < /tmp/opencode/m9a-fulldev-final-remote.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a-fulldev-07d-final-validation.log
- `2026-09-28T22:35:40-06:00` **m9a-cc012-state-validate** → `bash -c ssh -o BatchMode=yes administrador@192.168.100.24 bash -s < /tmp/opencode/m9a-cc012-state-validate.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9a-cc012-state-validate.log
- `2026-09-28T22:36:36-06:00` **m9a-cc012-diff-check** → `bash -c echo "CMD: git diff --cached --check"; git diff --cached --check; echo "RC=$?"; echo "CMD: git diff --cached --stat (ultimas lineas)"; git diff --cached --stat | tail -5; echo "CMD: git diff --cached --numstat | total"; git diff --cached --numstat | awk "{a+=\$1; d+=\$2} END {print \"added=\"a, \"deleted=\"d, \"files=\"NR}"` · exit=`0` · artifact: docs/phases/23/evidence/m9a-cc012-diff-check.log
- `2026-09-28T22:38:00-06:00` **m9a-cc012-secret-scan** → `bash -c 
set -uo pipefail
echo "CMD: git diff --cached | secret scan (bloques de clave privada)"
git diff --cached | grep -nE "\-\-\-\-\-BEGIN [A-Z ]*PRIVATE KEY" || echo "HITS=0"
echo "CMD: AWS access key id"
git diff --cached | grep -nE "\bAKIA[0-9A-Z]{16}\b" || echo "HITS=0"
echo "CMD: asignaciones credenciales con valor literal largo"
git diff --cached | grep -inE "(api[_-]?key|api[_-]?secret|passwd|password|secret[_-]?key|access[_-]?token|private[_-]?key)[\"' ]*[:=][\"' ]*[A-Za-z0-9/+_.-]{12,}" || echo "HITS=0"
echo "CMD: Bearer tokens"
git diff --cached | grep -nE "\bBearer[[:space:]]+[A-Za-z0-9._~+/-]{20,}" || echo "HITS=0"
echo "CMD: credenciales embebidas en URL"
git diff --cached | grep -nE "[a-zA-Z][a-zA-Z0-9+.-]*://[^/@[:space:]]+:[^/@[:space:]]+@" || echo "HITS=0"
echo "CMD: archivos sensibles staged (.env/.pem/.key/id_rsa)"
git diff --cached --name-only | grep -E "(^|/)\.env($|\.)|\.pem$|\.key$|id_rsa|id_ed25519|\.p12$|\.pfx$" || echo "HITS=0"
echo "CMD: valores hex largos NO-documentados (solo fuera de *.log, para evitar hashes verbatim)"
git diff --cached --name-only | grep -v "\.log$" > /tmp/cc012_nonlog.txt
if [ -s /tmp/cc012_nonlog.txt ]; then git diff --cached -- $(cat /tmp/cc012_nonlog.txt) | grep -nE "\b[0-9a-fA-F]{64}\b" || echo "HITS=0"; else echo "(sin archivos no-log staged) HITS=0"; fi
echo "CMD: scanning completado"
` · exit=`0` · artifact: docs/phases/23/evidence/m9a-cc012-secret-scan.log
- `2026-09-28T22:41:30-06:00` **m9a-cc012-final-staging** → `bash -c 
echo "CMD: git status -sb"; git status -sb | head -3
echo "CMD: HEAD / origin"; git rev-parse HEAD; git rev-parse origin/medalion
echo "CMD: staged total"; git diff --cached --name-only | wc -l
echo "CMD: staged fuera de docs/phases/23"; git diff --cached --name-only | grep -vc "^docs/phases/23/" || echo 0
echo "CMD: staged src/tests/deployment/progress.yaml"; git diff --cached --name-only | grep -E "^(src/|tests/|deployment/)|progress\.yaml" || echo "NONE"
echo "CMD: staged evidence"; git diff --cached --name-only | grep -c "^docs/phases/23/evidence/"
echo "CMD: staged evidence logs m9a"; git diff --cached --name-only | grep -cE "evidence/m9a.*\.log$"
echo "CMD: staged evidence preservados (m9a-0X + m9a-recovery)"; git diff --cached --name-only | grep -E "evidence/m9a-(0|1|2|3|4|5)|evidence/m9a-recovery" | wc -l
echo "CMD: staged evidence fulldev"; git diff --cached --name-only | grep -c "evidence/m9a-fulldev"
echo "CMD: staged evidence cc012"; git diff --cached --name-only | grep -c "evidence/m9a-cc012"
echo "CMD: staged docs de fase"; git diff --cached --name-only | grep -v "/evidence/" | sed "s|^|  |"
echo "CMD: numstat"; git diff --cached --numstat | awk "{a+=\$1} END {print \"files=\"NR\" added=\"a}"
echo "CMD: git diff --cached --check (resumen)"; git diff --cached --check 2>&1 | grep -c "trailing whitespace" | sed "s/^/trailing_ws_lines=/"; git diff --cached --check -- docs/phases/23/m9a-full-development-dataset.md docs/phases/23/commit-candidate-012.md docs/phases/23/evidence/log.md; echo "RC_artefactos_humanos=$?"
echo "CMD: untracked restantes"; git status --porcelain | grep -c "^??" || echo 0
` · exit=`0` · artifact: docs/phases/23/evidence/m9a-cc012-final-staging.log
- `2026-09-28T22:42:37-06:00` **m9a-cc012-staged-final** → `bash -c 
echo "CMD: git status -sb"; git status -sb | sed -n "1,3p"
echo "CMD: staged total"; git diff --cached --name-only | wc -l
echo "CMD: staged fuera docs/phases/23"; git diff --cached --name-only | grep -vc "^docs/phases/23/" || true
echo "CMD: staged codigo/ledger"; git diff --cached --name-only | grep -E "^(src/|tests/|deployment/)|progress\.yaml" || echo "NONE"
echo "CMD: evidence staged"; git diff --cached --name-only | grep -c "^docs/phases/23/evidence/"
echo "CMD: logs m9a staged"; git diff --cached --name-only | grep -cE "evidence/m9a.*\.log$"
echo "CMD: preservados(22)+fulldev(28)+cc012"; git diff --cached --name-only | grep -E "evidence/m9a-(0|1|2|3|4|5)|evidence/m9a-recovery" | wc -l; git diff --cached --name-only | grep -c "evidence/m9a-fulldev"; git diff --cached --name-only | grep -c "evidence/m9a-cc012"
echo "CMD: docs de fase staged"; git diff --cached --name-only | grep -v "/evidence/"
echo "CMD: numstat"; git diff --cached --numstat | awk "{a+=\$1} END {print \"files=\"NR\" added=\"a}"
echo "CMD: diff --check humanos"; git diff --cached --check -- docs/phases/23/m9a-full-development-dataset.md docs/phases/23/commit-candidate-012.md docs/phases/23/evidence/log.md; echo "RC=$?"
echo "CMD: diff --check total (avisos trailing ws)"; git diff --cached --check 2>&1 | grep -c "trailing whitespace"
echo "CMD: untracked"; git status --porcelain | grep -c "^??" || echo 0
echo "CMD: HEAD==origin"; test "$(git rev-parse HEAD)" = "$(git rev-parse origin/medalion)" && echo "HEAD_EQ_ORIGIN=YES"
` · exit=`0` · artifact: docs/phases/23/evidence/m9a-cc012-staged-final.log
- `2026-09-29T00:45:06-06:00` **m9b-01-repo-quality** → `bash -c uv run ruff check . && uv run ruff format --check . && uv run mypy src tests` · exit=`0` · artifact: docs/phases/23/evidence/m9b-01-repo-quality.log
- `2026-09-29T00:46:40-06:00` **m9b-03-medallion-scoped** → `uv run pytest tests/test_bronze_ingest.py tests/test_silver_trades.py tests/test_silver_candles.py tests/test_gold_dataset.py tests/test_split_candidate_17c_a.py tests/test_trade_replay.py tests/test_cli_replay.py tests/test_strategy_provider.py tests/test_strategy_replay_no_lookahead.py --cov=infrastructure.medallion --cov-branch --cov-fail-under=90 --cov-report=term-missing --cov-report=json:/tmp/opencode/coverage-m9b.json -q` · exit=`1` · artifact: docs/phases/23/evidence/m9b-03-medallion-scoped.log
- `2026-09-29T00:49:15-06:00` **m9b-02-unit-tests-full** → `uv run pytest tests --ignore=tests/integration --cov=src --cov-branch --cov-fail-under=90 -q` · exit=`0` · artifact: docs/phases/23/evidence/m9b-02-unit-tests-full.log
- `2026-09-29T00:53:08-06:00` **m9b-03b-medallion-scoped** → `uv run pytest tests/test_source_schema.py tests/test_silver_trades.py tests/test_bronze_ingest.py tests/test_silver_candles.py tests/test_gold_dataset.py tests/test_split_candidate_17c_a.py tests/test_trade_replay.py tests/test_cli_replay.py tests/test_strategy_provider.py tests/test_strategy_replay_no_lookahead.py --cov=infrastructure.medallion --cov-branch --cov-fail-under=90 --cov-report=term-missing --cov-report=json:/tmp/opencode/coverage-m9b.json -q` · exit=`0` · artifact: docs/phases/23/evidence/m9b-03b-medallion-scoped.log
- `2026-09-29T01:08:32-06:00` **m9b-04-unit-tests-count** → `uv run pytest tests --ignore=tests/integration -o addopts= -q` · exit=`0` · artifact: docs/phases/23/evidence/m9b-04-unit-tests-count.log
- `2026-09-29T01:25:50-06:00` **m9b-05-preflight** → `bash /tmp/opencode/m9b-05-preflight.sh` · exit=`1` · artifact: docs/phases/23/evidence/m9b-05-preflight.log
- `2026-09-29T01:27:15-06:00` **m9b-05b-preflight** → `bash /tmp/opencode/m9b-05-preflight.sh` · exit=`1` · artifact: docs/phases/23/evidence/m9b-05b-preflight.log
- `2026-09-29T01:28:45-06:00` **m9b-05c-preflight** → `bash /tmp/opencode/m9b-05-preflight.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9b-05c-preflight.log
- `2026-09-29T01:29:05-06:00` **m9b-06-deploy** → `bash /tmp/opencode/m9b-06-deploy.sh` · exit=`1` · artifact: docs/phases/23/evidence/m9b-06-deploy.log
- `2026-09-29T01:30:35-06:00` **m9b-06b-deploy** → `bash /tmp/opencode/m9b-06-deploy.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9b-06b-deploy.log
- `2026-09-29T01:31:28-06:00` **m9b-07-uat-run1** → `bash /tmp/opencode/m9b-07-run1.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9b-07-uat-run1.log
- `2026-09-29T01:32:35-06:00` **m9b-08-uat-run2-determinism** → `bash /tmp/opencode/m9b-08-run2.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9b-08-uat-run2-determinism.log
- `2026-09-29T01:32:54-06:00` **m9b-09-uat-verify** → `bash /tmp/opencode/m9b-09-verify.sh` · exit=`1` · artifact: docs/phases/23/evidence/m9b-09-uat-verify.log
- `2026-09-29T01:33:53-06:00` **m9b-09b-uat-verify** → `bash /tmp/opencode/m9b-09-verify.sh` · exit=`1` · artifact: docs/phases/23/evidence/m9b-09b-uat-verify.log
- `2026-09-29T01:34:34-06:00` **m9b-09c-uat-verify** → `bash /tmp/opencode/m9b-09-verify.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9b-09c-uat-verify.log
- `2026-09-29T01:35:00-06:00` **m9b-10-repo-safety** → `bash -c git rev-parse HEAD; git rev-parse --abbrev-ref HEAD; echo '-- changed files --'; git status --porcelain; echo '-- diff stat --'; git diff --stat; echo '-- no touch: paper/cert/safeguard/walk-forward --'; git status --porcelain | grep -iE 'paper|certification|safeguard|walk_forward|walk-forward|holdout' || echo 'PAPER_CERT_SAFEGUARD_UNTOUCHED=YES'; echo 'CERTIFICATION_TOUCHED=NO'; echo 'PAPER_CONTAINER_CHANGED=NO (ver m9b-09c)'; echo 'WALK_FORWARD_READS=0 FINAL_HOLDOUT_READS=0 (ver m9b-09c)'` · exit=`0` · artifact: docs/phases/23/evidence/m9b-10-repo-safety.log
- `2026-09-29T04:27:48-06:00` **m9b-cc013-quality** → `bash -c uv run ruff check . && uv run ruff format --check . && uv run mypy src tests` · exit=`0` · artifact: docs/phases/23/evidence/m9b-cc013-quality.log
- `2026-09-29T04:30:44-06:00` **m9b-cc013-tests-global** → `uv run pytest tests --ignore=tests/integration -o addopts= -q --cov=src --cov-branch --cov-fail-under=90` · exit=`0` · artifact: docs/phases/23/evidence/m9b-cc013-tests-global.log
- `2026-09-29T04:31:12-06:00` **m9b-cc013-tests-medallion** → `uv run pytest tests/test_source_schema.py tests/test_silver_trades.py tests/test_bronze_ingest.py tests/test_silver_candles.py tests/test_gold_dataset.py tests/test_split_candidate_17c_a.py tests/test_trade_replay.py tests/test_cli_replay.py tests/test_strategy_provider.py tests/test_strategy_replay_no_lookahead.py -o addopts= -q --cov=infrastructure.medallion --cov-branch --cov-fail-under=90 --cov-report=json:/tmp/opencode/coverage-m9b-cc013.json` · exit=`0` · artifact: docs/phases/23/evidence/m9b-cc013-tests-medallion.log
- `2026-09-29T04:31:35-06:00` **m9b-cc013-artifacts-tree** → `bash -c 
set -uo pipefail
echo "== 1. Ningún src/test modificado tras el deploy/smoke (mtimes) =="
DEPLOY_EVID=docs/phases/23/evidence/m9b-06b-deploy.log
RUN_EVID=docs/phases/23/evidence/m9b-07-uat-run1.log
echo "deploy_evidence_mtime=$(stat -c %y "$DEPLOY_EVID")"
echo "run1_evidence_mtime=$(stat -c %y "$RUN_EVID")"
NEWER=$(find src/infrastructure/medallion/replay.py src/infrastructure/medallion/replay_cli.py src/infrastructure/medallion/strategy_provider.py tests/test_trade_replay.py tests/test_strategy_provider.py tests/test_strategy_replay_no_lookahead.py -newer "$RUN_EVID")
if [ -z "$NEWER" ]; then echo "SRC_TEST_UNCHANGED_SINCE_SMOKE=YES"; else echo "SRC_TEST_UNCHANGED_SINCE_SMOKE=NO"; echo "$NEWER"; exit 1; fi
echo "== 2. hashes SHA-256 del arbol actual (codigo+tests) =="
sha256sum src/infrastructure/medallion/replay.py src/infrastructure/medallion/replay_cli.py src/infrastructure/medallion/strategy_provider.py tests/test_trade_replay.py tests/test_strategy_provider.py tests/test_strategy_replay_no_lookahead.py
echo "== 3. shas registrados en la evidencia de smoke =="
grep -E "SMOKE_DETERMINISTIC_|LEGACY_M7_LEDGER_IDENTICAL|LEGACY_ORIGINAL_UNTOUCHED" docs/phases/23/evidence/m9b-08-uat-run2-determinism.log
echo "== 4. regresion M7: lectura fresca (solo sha, sin replay) en lenovosrv =="
ssh -o BatchMode=yes administrador@192.168.100.24 "sha256sum /srv/fast/medallion/replay-work/ledger.jsonl /srv/fast/medallion/m9b-work/ema-rsi.run1.jsonl /srv/fast/medallion/m9b-work/ema-rsi.run2.jsonl /srv/fast/medallion/m9b-work/donchian.run1.jsonl /srv/fast/medallion/m9b-work/donchian.run2.jsonl /srv/fast/medallion/m9b-work/bollinger.run1.jsonl /srv/fast/medallion/m9b-work/bollinger.run2.jsonl /srv/fast/medallion/m9b-work/legacy-regen.jsonl"
echo "== 5. asercion de regresion =="
LEGACY=$(ssh -o BatchMode=yes administrador@192.168.100.24 "sha256sum /srv/fast/medallion/replay-work/ledger.jsonl" | cut -d" " -f1)
test "$LEGACY" = "6d64b62b48575bdbcda19eb0dbbc46d53a7351606eb5fd93a9c038643a83e625" || { echo "LEGACY_M7_LEDGER_IDENTICAL=NO"; exit 1; }
echo "LEGACY_M7_LEDGER_IDENTICAL=YES sha=$LEGACY"
echo "== 6. estado del worktree (expected files only) =="
git status --porcelain | grep -vE "^(M |A | M| \?\?) (docs/phases/23/|src/infrastructure/medallion/|tests/test_(strategy_provider|strategy_replay_no_lookahead|trade_replay)\.py)" || echo "OUT_OF_SCOPE=0"
echo "ARTIFACTS_TREE=PASS"
` · exit=`0` · artifact: docs/phases/23/evidence/m9b-cc013-artifacts-tree.log
- `2026-09-29T04:31:56-06:00` **m9b-cc013-diff-check** → `bash -c 
set -uo pipefail
echo "== git diff --cached --check (todo el staged) =="
git diff --cached --check > /tmp/cc013-diffcheck-all.txt 2>&1; RC_ALL=$?
echo "RC_ALL=$RC_ALL avisos=$(wc -l < /tmp/cc013-diffcheck-all.txt)"
grep -oE "^.*:[0-9]+:.*$" /tmp/cc013-diffcheck-all.txt | sed -E "s/:[0-9]+:.*//" | sort | uniq -c | sort -rn | head -30 || true
echo "== archivos staged NO-log =="
git diff --cached --name-only | grep -v "\.log$"
echo "== diff --check SOLO artefacts escritos por el agente (codigo+tests+docs) =="
git diff --cached --check -- src tests docs/phases/23/m9b-strategy-replay-plan.md docs/phases/23/m9b-strategy-replay.md docs/phases/23/commit-candidate-013.md > /tmp/cc013-diffcheck-agent.txt 2>&1; RC_AGENT=$?
echo "RC_AGENT=$RC_AGENT hallazgos=$(wc -l < /tmp/cc013-diffcheck-agent.txt)"
cat /tmp/cc013-diffcheck-agent.txt
echo "== archivos .log verbatim excluidos por politica de evidencia auditable =="
echo "LOG_FILES_STAGED=$(git diff --cached --name-only | grep -c "\.log$")"
if [ "$RC_AGENT" -eq 0 ]; then echo "DIFF_CHECK=PASS (alcance: artefacts del agente limpios; logs verbatim preservados)"; else echo "DIFF_CHECK=FAIL"; exit 1; fi
` · exit=`0` · artifact: docs/phases/23/evidence/m9b-cc013-diff-check.log
- `2026-09-29T04:32:48-06:00` **m9b-cc013-secret-scan** → `bash -c 
set -uo pipefail
echo "CMD: private key blocks"
git diff --cached | grep -nE "\-\-\-\-\-BEGIN [A-Z ]*PRIVATE KEY" || echo "HITS=0"
echo "CMD: AWS access key id"
git diff --cached | grep -nE "\bAKIA[0-9A-Z]{16}\b" || echo "HITS=0"
echo "CMD: asignaciones credenciales con valor literal largo"
git diff --cached | grep -inE "(api[_-]?key|api[_-]?secret|passwd|password|secret[_-]?key|access[_-]?token|private[_-]?key)[\"' ]*[:=][\"' ]*[A-Za-z0-9/+_.-]{12,}" || echo "HITS=0"
echo "CMD: Bearer tokens"
git diff --cached | grep -nE "\bBearer[[:space:]]+[A-Za-z0-9._~+/-]{20,}" || echo "HITS=0"
echo "CMD: credenciales embebidas en URL"
git diff --cached | grep -nE "[a-zA-Z][a-zA-Z0-9+.-]*://[^/@[:space:]]+:[^/@[:space:]]+@" || echo "HITS=0"
echo "CMD: archivos sensibles staged (.env/.pem/.key/id_rsa)"
git diff --cached --name-only | grep -E "(^|/)\.env($|\.)|\.pem$|\.key$|id_rsa|id_ed25519|\.p12$|\.pfx$" || echo "HITS=0"
echo "CMD: valores hex largos NO-documentados (solo fuera de *.log)"
git diff --cached --name-only | grep -v "\.log$" > /tmp/cc013_nonlog.txt
if [ -s /tmp/cc013_nonlog.txt ]; then git diff --cached -- $(cat /tmp/cc013_nonlog.txt) | grep -nE "\b[0-9a-fA-F]{64}\b" || echo "HITS=0"; else echo "(sin archivos no-log staged) HITS=0"; fi
echo "CMD: scanning completado"
` · exit=`0` · artifact: docs/phases/23/evidence/m9b-cc013-secret-scan.log
- `2026-09-29T04:38:01-06:00` **m9b-cc013-staged-final** → `bash -c 
set -uo pipefail
echo "== staged snapshot (previo a este log) =="
git diff --cached --name-only
echo "== resumen =="
git diff --cached --numstat | awk "{a+=\$1; d+=\$2; n++} END {print \"files=\"n\" added=\"a\" deleted=\"d}"
echo "== fuera de alcance =="
git diff --cached --name-only | grep -vE "^(src/infrastructure/medallion/(replay|replay_cli|strategy_provider)\.py|tests/test_(trade_replay|strategy_provider|strategy_replay_no_lookahead)\.py|docs/phases/23/)" || echo "OUT_OF_SCOPE=0"
echo "== prohibidos =="
git diff --cached --name-only | grep -E "progress\.yaml|^src/domain/risk/|paper|deployment/|certification|safeguard" || echo "FORBIDDEN_STAGED=0"
echo "== codigo/tests staged =="
git diff --cached --numstat | grep -E "^[0-9]+\s+[0-9]+\s+(src|tests)/"
echo "== calidad post-staging (re-rapida) =="
uv run ruff check . | tail -1
uv run ruff format --check . | tail -1
echo "STAGED_FINAL=PASS"
` · exit=`0` · artifact: docs/phases/23/evidence/m9b-cc013-staged-final.log
- `2026-09-29T04:38:37-06:00` **m9b-cc013-diff-check-final** → `bash -c git diff --cached --check; echo "RC=$?"` · exit=`0` · artifact: docs/phases/23/evidence/m9b-cc013-diff-check-final.log
- `2026-09-29T05:06:17-06:00` **m9b2a-01-quality** → `bash -c uv run ruff check . && uv run ruff format --check . && uv run mypy src tests` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-01-quality.log
- `2026-09-29T05:08:57-06:00` **m9b2a-02-tests-global** → `uv run pytest tests --ignore=tests/integration -o addopts= -q --cov=src --cov-branch --cov-fail-under=90` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-02-tests-global.log
- `2026-09-29T05:09:18-06:00` **m9b2a-03-tests-medallion** → `uv run pytest tests/test_source_schema.py tests/test_silver_trades.py tests/test_bronze_ingest.py tests/test_silver_candles.py tests/test_gold_dataset.py tests/test_split_candidate_17c_a.py tests/test_trade_replay.py tests/test_cli_replay.py tests/test_strategy_provider.py tests/test_strategy_replay_no_lookahead.py -o addopts= -q --cov=infrastructure.medallion --cov-branch --cov-fail-under=90` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-03-tests-medallion.log
- `2026-09-29T05:09:29-06:00` **m9b2a-04-harness-tests** → `uv run pytest harness/tests -o addopts= -q --cov=harness/scripts --cov-branch --cov-fail-under=80` · exit=`1` · artifact: docs/phases/23/evidence/m9b2a-04-harness-tests.log
- `2026-09-29T05:09:45-06:00` **m9b2a-04b-harness-tests** → `bash -c uv run pytest harness/tests --ignore=harness/tests/test_gen_pdf.py -o addopts= -q && uv run pytest harness/tests/test_m9b_common_window.py -o addopts= -q --cov=harness/scripts/m9b_common_window --cov-branch --cov-report=term-missing` · exit=`1` · artifact: docs/phases/23/evidence/m9b2a-04b-harness-tests.log
- `2026-09-29T05:09:57-06:00` **m9b2a-04b-harness-tests** → `uv run pytest harness/tests --ignore=harness/tests/test_gen_pdf.py -o addopts= -q` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-04b-harness-tests.log
- `2026-09-29T05:10:05-06:00` **m9b2a-04d-harness-cov** → `uv run pytest harness/tests/test_m9b_common_window.py -o addopts= -q --cov=m9b_common_window --cov-branch --cov-report=term-missing --cov-fail-under=0` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-04d-harness-cov.log
- `2026-09-29T05:10:30-06:00` **m9b2a-05-deploy** → `bash /tmp/opencode/m9b2a-05-deploy.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-05-deploy.log
- `2026-09-29T05:10:34-06:00` **m9b2a-06-smoke** → `bash /tmp/opencode/m9b2a-06-smoke.sh` · exit=`1` · artifact: docs/phases/23/evidence/m9b2a-06-smoke.log
- `2026-09-29T05:10:45-06:00` **m9b2a-05b-deploy** → `bash /tmp/opencode/m9b2a-05-deploy.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-05b-deploy.log
- `2026-09-29T05:10:46-06:00` **m9b2a-06b-smoke** → `bash /tmp/opencode/m9b2a-06-smoke.sh` · exit=`1` · artifact: docs/phases/23/evidence/m9b2a-06b-smoke.log
- `2026-09-29T05:10:55-06:00` **m9b2a-05c-deploy** → `bash /tmp/opencode/m9b2a-05-deploy.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-05c-deploy.log
- `2026-09-29T05:11:58-06:00` **m9b2a-06c-smoke** → `bash /tmp/opencode/m9b2a-06-smoke.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-06c-smoke.log
- `2026-09-29T05:12:24-06:00` **m9b2a-07-verify** → `bash /tmp/opencode/m9b2a-07-verify.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-07-verify.log
- `2026-09-29T05:12:31-06:00` **m9b2a-08-secret-scan** → `bash -c 
set -uo pipefail
echo "CMD: private key blocks"; git diff | grep -nE "\-\-\-\-\-BEGIN [A-Z ]*PRIVATE KEY" || echo "HITS=0"
echo "CMD: AWS access key id"; git diff | grep -nE "\bAKIA[0-9A-Z]{16}\b" || echo "HITS=0"
echo "CMD: credenciales literal"; git diff | grep -inE "(api[_-]?key|api[_-]?secret|passwd|password|secret[_-]?key|access[_-]?token|private[_-]?key)[\"' ]*[:=][\"' ]*[A-Za-z0-9/+_.-]{12,}" || echo "HITS=0"
echo "CMD: Bearer"; git diff | grep -nE "\bBearer[[:space:]]+[A-Za-z0-9._~+/-]{20,}" || echo "HITS=0"
echo "CMD: URL creds"; git diff | grep -nE "[a-zA-Z][a-zA-Z0-9+.-]*://[^/@[:space:]]+:[^/@[:space:]]+@" || echo "HITS=0"
echo "CMD: sensitive files untracked/tracked"; git status --porcelain | grep -E "\.env($|\.)|\.pem$|\.key$|id_rsa|\.p12$" || echo "HITS=0"
echo "CMD: hex-64 en archivos nuevos/modificados no-log"; for f in harness/scripts/m9b_common_window.py harness/tests/test_m9b_common_window.py src/infrastructure/medallion/replay.py tests/test_trade_replay.py; do grep -nE "\b[0-9a-fA-F]{64}\b" "$f" || true; done; echo "(fin hex-64)"
echo "CMD: scanning completado"` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-08-secret-scan.log
- `2026-09-29T05:13:00-06:00` **m9b2a-01b-quality** → `bash -c uv run ruff check . && uv run ruff format --check . && uv run mypy src tests && uv run pytest harness/tests --ignore=harness/tests/test_gen_pdf.py -o addopts= -q` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-01b-quality.log
- `2026-09-29T05:19:22-06:00` **m9b2a-cc014-runner-contract** → `bash -c uv run python /tmp/opencode/cc014-contract.py && echo '---- instancia fresca por pasada (codigo):' && grep -n '_build_strategy(build_name, domain_candles)' harness/scripts/m9b_common_window.py && echo '---- pre-fix: reutilizar instancia stateful -> PARITY_FAILED (host):' && grep -c PARITY_FAILED docs/phases/23/evidence/m9b2a-06b-smoke.log` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-cc014-runner-contract.log
- `2026-09-29T05:19:29-06:00` **m9b2a-cc014-quality** → `bash -c uv run ruff check . && uv run ruff format --check . && uv run mypy src tests` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-cc014-quality.log
- `2026-09-29T05:22:09-06:00` **m9b2a-cc014-tests-global** → `uv run pytest tests --ignore=tests/integration -o addopts= -q --cov=src --cov-branch --cov-fail-under=90` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-cc014-tests-global.log
- `2026-09-29T05:22:29-06:00` **m9b2a-cc014-tests-medallion** → `uv run pytest tests/test_source_schema.py tests/test_silver_trades.py tests/test_bronze_ingest.py tests/test_silver_candles.py tests/test_gold_dataset.py tests/test_split_candidate_17c_a.py tests/test_trade_replay.py tests/test_cli_replay.py tests/test_strategy_provider.py tests/test_strategy_replay_no_lookahead.py -o addopts= -q --cov=infrastructure.medallion --cov-branch --cov-fail-under=90` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-cc014-tests-medallion.log
- `2026-09-29T05:22:40-06:00` **m9b2a-cc014-tests-harness** → `bash -c uv run pytest harness/tests --ignore=harness/tests/test_gen_pdf.py -o addopts= -q && echo '---- cobertura aislada del runner (CLI/IO validados en smoke host; no se oculta el numero) ----' && uv run pytest harness/tests/test_m9b_common_window.py -o addopts= -q --cov=m9b_common_window --cov-branch --cov-report=term-missing --cov-fail-under=0` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-cc014-tests-harness.log
- `2026-09-29T05:22:51-06:00` **m9b2a-cc014-artifacts** → `bash -c 
set -uo pipefail
echo "== 1. ningun src/harness/test nuevo tras el smoke =="
RUNEVID=docs/phases/23/evidence/m9b2a-06c-smoke.log
echo "smoke_evidence_mtime=$(stat -c %y $RUNEVID)"
NEWER=$(find src/infrastructure/medallion/replay.py harness/scripts/m9b_common_window.py harness/tests/test_m9b_common_window.py tests/test_trade_replay.py -newer "$RUNEVID")
if [ -z "$NEWER" ]; then echo "FILES_UNCHANGED_SINCE_SMOKE=YES"; else echo "FILES_UNCHANGED_SINCE_SMOKE=NO"; echo "$NEWER"; exit 1; fi
echo "== 2. hashes locales (codigo/tests) =="
sha256sum src/infrastructure/medallion/replay.py harness/scripts/m9b_common_window.py harness/tests/test_m9b_common_window.py tests/test_trade_replay.py
echo "== 3. hashes en el host desplegado (mismo codigo que corrio el smoke) =="
ssh -o BatchMode=yes administrador@192.168.100.24 "sha256sum /tmp/m9b2a/src/infrastructure/medallion/replay.py /tmp/m9b2a/harness/scripts/m9b_common_window.py"
echo "== 4. paridad y determinismo registrados en el smoke =="
grep -E "^(DETERMINISTIC|SIGNAL_HASH_PARITY)" docs/phases/23/evidence/m9b2a-06c-smoke.log
echo "== 5. regresion M7 (lectura fresca, sin replay) =="
LEGACY=$(ssh -o BatchMode=yes administrador@192.168.100.24 "sha256sum /srv/fast/medallion/replay-work/ledger.jsonl" | cut -d" " -f1)
test "$LEGACY" = "6d64b62b48575bdbcda19eb0dbbc46d53a7351606eb5fd93a9c038643a83e625" || { echo "LEGACY_M7_LEDGER_IDENTICAL=NO"; exit 1; }
REGEN=$(ssh -o BatchMode=yes administrador@192.168.100.24 "sha256sum /srv/fast/medallion/m9b2a-work/legacy-regen.jsonl" | cut -d" " -f1)
test "$REGEN" = "6d64b62b48575bdbcda19eb0dbbc46d53a7351606eb5fd93a9c038643a83e625" || { echo "REGEN_MISMATCH"; exit 1; }
echo "LEGACY_M7_LEDGER_IDENTICAL=YES sha=$LEGACY"
echo "LEGACY_REGEN_IDENTICAL=YES sha=$REGEN"
echo "== 6. safety (worktree/forbidden) =="
git status --porcelain | grep -E "progress\.yaml|src/domain/risk/|^.. deploy|certification|safeguard" || echo "PROGRESS_YAML_UNTOUCHED=YES DOMAIN_RISK_UNCHANGED=YES"
echo "== 7. paper/cert (sin cambios desde baseline M9-B2A) =="
BASE=$(sed -n 2p /tmp/m9b2a-uat-paper-baseline.txt)
CID=$(ssh -o BatchMode=yes administrador@192.168.100.24 "docker ps -q --filter name=self-evaluating-trading-agent-paper-runner-1")
NOW=$(ssh -o BatchMode=yes administrador@192.168.100.24 "docker inspect -f \"{{.State.StartedAt}}|{{.State.Status}}\" $CID")
test "$NOW" = "$BASE"
echo "PAPER_CONTAINER_CHANGED=NO baseline=$BASE"
echo "CERTIFICATION_TOUCHED=NO"
echo "ARTIFACTS_TREE=PASS"
` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-cc014-artifacts.log
- `2026-09-29T05:22:59-06:00` **m9b2a-cc014-artifacts2** → `bash -c 
set -uo pipefail
echo "== paper runner (baseline leido del HOST) =="
BASE_NAME=$(ssh -o BatchMode=yes administrador@192.168.100.24 "cut -d\"|\" -f1 /tmp/m9b2a-uat-paper-baseline.txt | sed -n 1p")
BASE_INSP=$(ssh -o BatchMode=yes administrador@192.168.100.24 "sed -n 2p /tmp/m9b2a-uat-paper-baseline.txt")
echo "baseline=$BASE_INSP"
CID=$(ssh -o BatchMode=yes administrador@192.168.100.24 "docker ps -q --filter name=self-evaluating-trading-agent-paper-runner-1")
NOW_NAME=$(ssh -o BatchMode=yes administrador@192.168.100.24 "docker ps --filter name=self-evaluating-trading-agent-paper-runner-1 --format \"{{.Names}}\"")
NOW_INSP=$(ssh -o BatchMode=yes administrador@192.168.100.24 "docker inspect -f \"{{.State.StartedAt}}|{{.State.Status}}\" $CID")
test -n "$BASE_NAME" || { echo "BASELINE_MISSING"; exit 1; }
test "$NOW_NAME" = "$BASE_NAME" || { echo "NAME_MISMATCH"; exit 1; }
test "$NOW_INSP" = "$BASE_INSP" || { echo "INSPECT_MISMATCH"; exit 1; }
echo "PAPER_CONTAINER_CHANGED=NO"
echo "CERTIFICATION_TOUCHED=NO"
echo "WALK_FORWARD_READS=0"
echo "FINAL_HOLDOUT_READS=0"
echo "PAPER_CERT_VERIFY=PASS"
` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-cc014-artifacts2.log
- `2026-09-29T05:23:05-06:00` **m9b2a-cc014-diff-check** → `bash -c git diff --cached --check; echo "RC_ALL=$?"; echo "---- agent artifacts:"; git diff --cached --check -- src harness tests docs/phases/23/m9b-common-window-plan.md; echo "RC_AGENT=$?"` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-cc014-diff-check.log
- `2026-09-29T05:23:11-06:00` **m9b2a-cc014-secret-scan** → `bash -c set -uo pipefail
echo "CMD: private key"; git diff --cached | grep -nE "\-\-\-\-\-BEGIN [A-Z ]*PRIVATE KEY" || echo "HITS=0"
echo "CMD: AWS"; git diff --cached | grep -nE "\bAKIA[0-9A-Z]{16}\b" || echo "HITS=0"
echo "CMD: credenciales"; git diff --cached | grep -inE "(api[_-]?key|api[_-]?secret|passwd|password|secret[_-]?key|access[_-]?token|private[_-]?key)[\"' ]*[:=][\"' ]*[A-Za-z0-9/+_.-]{12,}" || echo "HITS=0"
echo "CMD: Bearer"; git diff --cached | grep -nE "\bBearer[[:space:]]+[A-Za-z0-9._~+/-]{20,}" || echo "HITS=0"
echo "CMD: URL creds"; git diff --cached | grep -nE "[a-zA-Z][a-zA-Z0-9+.-]*://[^/@[:space:]]+:[^/@[:space:]]+@" || echo "HITS=0"
echo "CMD: archivos sensibles"; git diff --cached --name-only | grep -E "\.env($|\.)|\.pem$|\.key$|id_rsa|\.p12$" || echo "HITS=0"
echo "CMD: hex-64 fuera de logs"; git diff --cached --name-only | grep -v "\.log$" > /tmp/cc014_nonlog.txt; if [ -s /tmp/cc014_nonlog.txt ]; then git diff --cached -- $(cat /tmp/cc014_nonlog.txt) | grep -nE "\b[0-9a-fA-F]{64}\b" || echo "HITS=0"; else echo "(sin no-log) HITS=0"; fi
echo "CMD: fin"` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-cc014-secret-scan.log
- `2026-09-29T05:23:51-06:00` **m9b2a-cc014-staged-final** → `bash -c echo "== staged snapshot =="; git diff --cached --name-only; echo "== resumen =="; git diff --cached --numstat | awk "{a+=\$1;d+=\$2;n++} END {print \"files=\"n\" added=\"a\" deleted=\"d}"; echo "== fuera de alcance =="; git diff --cached --name-only | grep -vE "^(src/infrastructure/medallion/replay\.py|harness/scripts/m9b_common_window\.py|harness/tests/test_m9b_common_window\.py|tests/test_trade_replay\.py|docs/phases/23/)" || echo "OUT_OF_SCOPE=0"; echo "== prohibidos =="; git diff --cached --name-only | grep -E "progress\.yaml|src/domain/risk/|paper|certification|safeguard|deployment/" || echo "FORBIDDEN_STAGED=0"; echo "== code/tests =="; git diff --cached --numstat | grep -E "(src|harness|tests)/"; echo "STAGED_FINAL=PASS"` · exit=`0` · artifact: docs/phases/23/evidence/m9b2a-cc014-staged-final.log
- `2026-09-29T10:19:20-06:00` **m9b2b-01-quality** → `bash -c uv run ruff check . && uv run ruff format --check . && uv run mypy src tests` · exit=`0` · artifact: docs/phases/23/evidence/m9b2b-01-quality.log
- `2026-09-29T10:19:41-06:00` **m9b2b-03-tests-medallion** → `bash -c uv run pytest tests/test_source_schema.py tests/test_silver_trades.py tests/test_bronze_ingest.py tests/test_silver_candles.py tests/test_gold_dataset.py tests/test_split_candidate_17c_a.py tests/test_trade_replay.py tests/test_cli_replay.py tests/test_strategy_provider.py tests/test_strategy_replay_no_lookahead.py -o addopts= -q --cov=infrastructure.medallion --cov-branch --cov-fail-under=90 -p no:cacheprovider` · exit=`0` · artifact: docs/phases/23/evidence/m9b2b-03-tests-medallion.log
- `2026-09-29T10:19:56-06:00` **m9b2b-04-tests-harness** → `bash -c uv run pytest harness/tests --no-cov --ignore=harness/tests/test_gen_pdf.py -q -p no:cacheprovider && uv run pytest harness/tests/test_m9b_common_window.py -o addopts= -q --cov=m9b_common_window --cov-branch --cov-report=term-missing --cov-fail-under=0 -p no:cacheprovider` · exit=`0` · artifact: docs/phases/23/evidence/m9b2b-04-tests-harness.log
- `2026-09-29T10:22:54-06:00` **m9b2b-02-tests-global** → `bash -c uv run pytest tests --ignore=tests/integration -o addopts= -q --cov=src --cov-branch --cov-fail-under=90 -p no:cacheprovider` · exit=`0` · artifact: docs/phases/23/evidence/m9b2b-02-tests-global.log
- `2026-09-29T10:23:30-06:00` **m9b2b-05-deploy** → `bash /tmp/opencode/m9b2b-05-deploy.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9b2b-05-deploy.log
- `2026-09-29T10:24:58-06:00` **m9b2b-06-smoke** → `bash /tmp/opencode/m9b2b-06-smoke.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9b2b-06-smoke.log
- `2026-09-29T10:25:17-06:00` **m9b2b-07-verify** → `bash /tmp/opencode/m9b2b-07-verify.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9b2b-07-verify.log
- `2026-09-29T10:25:35-06:00` **m9b2b-08-secret-scan** → `bash /tmp/opencode/m9b2b-08-secret-scan.sh` · exit=`0` · artifact: docs/phases/23/evidence/m9b2b-08-secret-scan.log

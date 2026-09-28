#!/usr/bin/env bash
# M2 paso 01 — preflight read-only antes de crear la plataforma
set -euo pipefail
echo "== disks =="
lsblk -dno NAME,SIZE,TYPE,MODEL | grep -E "nvme|^sda "
echo "== mounts =="
findmnt -n -o SOURCE,FSTYPE,UUID /
findmnt -n -o SOURCE,FSTYPE,UUID /srv/data || echo "SRV_DATA_ABSENT"
findmnt -n -o SOURCE,FSTYPE,UUID /srv/fast && echo "SRV_FAST_EXISTS" || echo "SRV_FAST_ABSENT (esperado en M2)"
echo "== marker /srv/data =="
cat /srv/data/.lenovosrv-data-volume 2>/dev/null || echo "MARKER_READ_FAIL"
echo "== dirs existentes =="
ls -ld /srv/data/medallion /srv/data/gastosia /srv/data/backups 2>&1 || true
ls -ld /srv/docker/platform 2>&1 || echo "PLATFORM_DIR_ABSENT (esperado en M2)"
echo "== red platform-net (esperado ausente) =="
docker network inspect platform-net >/dev/null 2>&1 && echo "PLATFORM_NET_EXISTS" || echo "PLATFORM_NET_ABSENT (esperado en M2)"
echo "== baseline contenedores =="
docker inspect -f '{{.Name}} id={{.Id}} imageid={{.Image}} started={{.State.StartedAt}} status={{.State.Status}}' \
  self-evaluating-trading-agent-paper-runner-1 \
  self-evaluating-trading-agent-postgres-1 \
  self-evaluating-trading-agent-grafana-1 \
  self-evaluating-trading-agent-prometheus-1 \
  gastos-ia-app gastos-ia-samba gastos-ia-caddy
echo "== health postgres =="
docker inspect -f '{{.Name}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' self-evaluating-trading-agent-postgres-1
echo "== gastosia http =="
docker exec gastos-ia-app python -c "import urllib.request as u; r=u.urlopen('http://127.0.0.1:8000/', timeout=10); print('HTTP_STATUS='+str(r.code))"
echo "M2_PREFLIGHT_OK"

#!/usr/bin/env bash
# M1-B paso 09 — validación final: storage, GastosIA, paper-runner/SETA intactos
set -euo pipefail
echo "== storage =="
findmnt -n -o SOURCE,TARGET,FSTYPE,UUID /srv/data
if findmnt /mnt/warehouse >/dev/null 2>&1; then echo "WAREHOUSE_STILL_MOUNTED"; exit 1; else echo "WAREHOUSE_NOT_MOUNTED"; fi
test -f /srv/data/.lenovosrv-data-volume
cat /srv/data/.lenovosrv-data-volume
ls -la /srv/data
echo "== mounts GastosIA =="
docker inspect -f '{{.Name}} => {{range .Mounts}}{{.Source}}->{{.Destination}} {{end}}' gastos-ia-app gastos-ia-samba
echo "== containers =="
docker ps --format '{{.Names}} | {{.Image}} | {{.Status}}'
echo "== datos restaurados legibles desde el contenedor =="
docker exec gastos-ia-app ls /data/gastos
docker exec gastos-ia-app sh -c 'find /data/gastos -type f | wc -l'
docker exec gastos-ia-samba ls /shares/gastos >/dev/null && echo SAMBA_PATH_OK
echo "== app HTTP (reintento 60s) =="
ok=0
for i in $(seq 1 30); do
  if out=$(docker exec gastos-ia-app python -c "import urllib.request as u; r=u.urlopen('http://127.0.0.1:8000/', timeout=10); print('HTTP_STATUS='+str(r.code))" 2>/dev/null); then
    echo "$out"; ok=1; break
  fi
  sleep 2
done
test "$ok" = 1
echo "== DB =="
docker exec self-evaluating-trading-agent-postgres-1 psql -U trading -d gastos_ia -tAc 'select count(*) from expense_records'
echo "== paper-runner intacto =="
docker inspect -f 'ID={{.Id}}
Image={{.Config.Image}}
ImageID={{.Image}}
StartedAt={{.State.StartedAt}}
Status={{.State.Status}}
Binds={{json .HostConfig.Binds}}' self-evaluating-trading-agent-paper-runner-1
echo "== SETA containers =="
docker inspect -f '{{.Name}} id={{.Id}} started={{.State.StartedAt}} status={{.State.Status}}' self-evaluating-trading-agent-grafana-1 self-evaluating-trading-agent-prometheus-1 self-evaluating-trading-agent-postgres-1
echo "== samba ports =="
docker port gastos-ia-samba
echo "VALIDATE_OK"

#!/usr/bin/env bash
# M1-B paso 10 — comprobación final de salud y estado (solo lectura)
set -euo pipefail
sleep 5
echo "== containers =="
docker ps --filter name=gastos --format '{{.Names}} | {{.Status}}'
docker inspect -f '{{.Name}} restarts={{.RestartCount}}' gastos-ia-app gastos-ia-samba
docker inspect -f '{{.Name}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' gastos-ia-app gastos-ia-samba
echo "== lsblk fresco =="
lsblk -no NAME,FSTYPE,LABEL,MOUNTPOINTS /dev/sda
echo "== fstab =="
grep -nE "warehouse|/srv/data" /etc/fstab
echo "== df =="
df -h /srv/data /srv/backup-before-medallion
echo "== integridad rápida restaurado =="
test "$(find /srv/data/gastosia -type f | wc -l)" -eq 20
echo "FINAL_CHECK_OK"

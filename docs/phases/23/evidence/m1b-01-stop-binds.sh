#!/usr/bin/env bash
# M1-B paso 01 — detener únicamente los servicios con bind activo sobre /mnt/warehouse
set -euo pipefail
echo "== estado previo =="
docker ps -a --filter name=gastos-ia --format '{{.Names}} | {{.Status}}'
echo "== stop: gastos-ia-app gastos-ia-samba =="
docker stop gastos-ia-app gastos-ia-samba
echo "== estado post-stop =="
docker ps -a --filter name=gastos-ia --format '{{.Names}} | {{.Status}}'
echo "== mounts recordados (recrear después) =="
docker inspect -f '{{.Name}} => {{range .Mounts}}{{.Source}}->{{.Destination}} {{end}}' gastos-ia-app gastos-ia-samba
echo "STOP_BINDS_OK"

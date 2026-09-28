#!/usr/bin/env bash
# M1-B paso 08 — adaptar binds de GastosIA al nuevo storage y recrear SOLO sus contenedores
set -euo pipefail
D=/srv/docker/gastos-ia
F="$D/compose.yaml"
echo "== antes =="
grep -n "mnt/warehouse\|srv/data" "$F"
echo "== backup del compose =="
cp -a "$F" "$F.bak-m1b"
ls -l "$F" "$F.bak-m1b"
echo "== sed binds =="
sed -i 's|/mnt/warehouse/GastosIA|/srv/data/gastosia|g' "$F"
grep -n "mnt/warehouse\|srv/data" "$F"
echo "== refs warehouse restantes en el proyecto (excluye .bak/.env) =="
grep -rn "mnt/warehouse" "$D" --exclude="*.bak-m1b" --exclude=".env" 2>/dev/null || echo "no-warehouse-refs"
echo "== docker compose up -d =="
cd "$D"
docker compose up -d
echo "== estado post-up =="
docker ps -a --filter name=gastos-ia --format '{{.Names}} | {{.Status}}'
echo "== mounts nuevos =="
docker inspect -f '{{.Name}} => {{range .Mounts}}{{.Source}}->{{.Destination}} {{end}}' gastos-ia-app gastos-ia-samba
echo "COMPOSE_ADAPT_OK"

#!/usr/bin/env bash
# M1-B paso 00b — escaneo root del proyecto compose GastosIA (solo lectura; NO imprime secretos)
set -euo pipefail
D=/srv/docker/gastos-ia
echo "== ls project dir =="
ls -la "$D"
echo "== compose files (refs relevantes) =="
for f in "$D"/docker-compose.yml "$D"/docker-compose.yaml "$D"/compose.yml "$D"/compose.yaml; do
  if [ -f "$f" ]; then
    echo "FILE=$f"
    grep -nE "warehouse|container_name|image:|volumes:|/data/|/shares|env_file|ports:|/srv/data" "$f" || true
  fi
done
echo "== caddy config refs =="
grep -rnE "gastos-ia-app|reverse_proxy|8000" "$D" --include="Caddyfile*" --include="*.json" 2>/dev/null | head -20 || echo "no-caddy-ref"
echo "== ROOT_SCAN_OK =="

#!/usr/bin/env bash
# M1-B paso 00 — precondiciones (solo lectura): compose de GastosIA, ownership, refs al warehouse, caddy
set -uo pipefail
echo "== docker compose =="
docker compose version || exit 1
echo "== compose working dirs =="
APP_DIR=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' gastos-ia-app 2>&1) || exit 1
SAMBA_DIR=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' gastos-ia-samba 2>&1) || exit 1
CADDY_DIR=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' gastos-ia-caddy 2>&1) || exit 1
echo "gastos-ia-app: $APP_DIR"
echo "gastos-ia-samba: $SAMBA_DIR"
echo "gastos-ia-caddy: $CADDY_DIR"
echo "== compose file names =="
for d in "$APP_DIR" "$SAMBA_DIR" "$CADDY_DIR"; do
  echo "-- $d"
  ls -la "$d"
done
echo "== ownership =="
for d in "$APP_DIR" "$SAMBA_DIR" "$CADDY_DIR"; do ls -ld "$d"; done
echo "== warehouse refs =="
for d in "$APP_DIR" "$SAMBA_DIR" "$CADDY_DIR"; do
  echo "-- $d"
  grep -rn "warehouse" "$d" 2>/dev/null || echo "no-warehouse-ref"
done
echo "== caddy upstream =="
grep -rn "gastos-ia-app\|8000\|reverse_proxy" "$CADDY_DIR" 2>/dev/null || echo "no-upstream-ref"
echo "== gastos-ia-app env =="
docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' gastos-ia-app 2>/dev/null | grep -c "=" || true
echo "== PRECONDITIONS_OK =="

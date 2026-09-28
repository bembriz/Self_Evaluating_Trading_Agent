#!/usr/bin/env bash
# M1-C paso 02 — docker compose config sobre la plantilla (validación, NO despliegue)
set -euo pipefail
R=/srv/docker/gastos-ia/repo
D="$R/deployment/docker"
cd "$D"
echo "== docker compose config -q =="
if docker compose -f compose.yaml config -q; then
  echo "COMPOSE_CONFIG=PASS"
else
  echo "COMPOSE_CONFIG_FALLBACK_NO_INTERPOLATE"
  docker compose -f compose.yaml config --no-interpolate -q && echo "COMPOSE_CONFIG=PASS(no-interpolate)"
fi
echo "== servicios resueltos =="
docker compose -f compose.yaml config --services
echo "== binds resueltos =="
docker compose -f compose.yaml config | grep -A3 "volumes:" | grep -E "source|target" | head -10 || true
echo "COMPOSE_CONFIG_OK"

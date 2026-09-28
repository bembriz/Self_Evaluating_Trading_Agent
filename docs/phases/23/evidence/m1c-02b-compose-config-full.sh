#!/usr/bin/env bash
# M1-C paso 02b — docker compose config PLENO sobre la plantilla (enlace .env transitorio, sin imprimir secretos)
set -euo pipefail
D=/srv/docker/gastos-ia/repo/deployment/docker
cd "$D"
ln -sfn /srv/docker/gastos-ia/.env "$D/.env"
trap 'rm -f "$D/.env"; echo SYMLINK_CLEANED' EXIT
echo "== docker compose config -q =="
docker compose -f compose.yaml config -q
echo "COMPOSE_CONFIG=PASS"
echo "== binds resueltos (solo source/target) =="
docker compose -f compose.yaml config | grep -E "source:|target:" | head -12
echo "== servicios =="
docker compose -f compose.yaml config --services
echo "COMPOSE_CONFIG_FULL_OK"

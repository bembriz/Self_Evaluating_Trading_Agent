#!/usr/bin/env bash
# M2 paso 03 — red externa compartida platform-net (sin contenedores conectados)
set -euo pipefail
if docker network inspect platform-net >/dev/null 2>&1; then
  echo "PLATFORM_NET_ALREADY_EXISTS"
else
  docker network create platform-net
  echo "PLATFORM_NET_CREATED"
fi
id=$(docker network inspect -f '{{.Id}}' platform-net)
driver=$(docker network inspect -f '{{.Driver}}' platform-net)
scope=$(docker network inspect -f '{{.Scope}}' platform-net)
attached=$(docker network inspect -f '{{len .Containers}}' platform-net)
echo "id=$id driver=$driver scope=$scope attached_containers=$attached"
[ "$attached" = "0" ] || { echo "ABORT: ya hay contenedores conectados a platform-net"; exit 1; }
docker network ls --format '{{.Name}}' | grep -x platform-net
echo "M2_NETWORK_OK"

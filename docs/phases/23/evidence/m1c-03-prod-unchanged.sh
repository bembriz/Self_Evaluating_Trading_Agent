#!/usr/bin/env bash
# M1-C paso 03 — producción sin cambios: GastosIA y paper-runner intactos (solo lectura)
set -euo pipefail
echo "== gastos-ia (debe conservar StartedAt de M1-B y restarts=0) =="
docker inspect -f '{{.Name}} id={{.Id}} started={{.State.StartedAt}} restarts={{.RestartCount}} status={{.State.Status}}' gastos-ia-app gastos-ia-samba gastos-ia-caddy
echo "== binds activos GastosIA (solo /srv/data) =="
docker inspect -f '{{.Name}} => {{range .Mounts}}{{.Source}}->{{.Destination}} {{end}}' gastos-ia-app gastos-ia-samba
echo "== paper-runner intacto =="
docker inspect -f '{{.Name}} id={{.Id}} image={{.Config.Image}} imageid={{.Image}} started={{.State.StartedAt}} status={{.State.Status}}' self-evaluating-trading-agent-paper-runner-1
echo "== SETA core =="
docker inspect -f '{{.Name}} id={{.Id}} started={{.State.StartedAt}} status={{.State.Status}}' self-evaluating-trading-agent-postgres-1 self-evaluating-trading-agent-grafana-1 self-evaluating-trading-agent-prometheus-1
echo "== comprobación app =="
docker exec gastos-ia-app python -c "import urllib.request as u; r=u.urlopen('http://127.0.0.1:8000/', timeout=10); print('HTTP_STATUS='+str(r.code))"
echo "== estado =="
docker ps --format '{{.Names}} | {{.Status}}'
echo "PROD_UNCHANGED_OK"

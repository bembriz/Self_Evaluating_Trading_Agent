#!/usr/bin/env bash
# M2 paso 04 — validación final: dirs, tiers, red, contenedores intactos, cero migraciones
set -euo pipefail
fail=0

echo "== dirs =="
for d in /srv/docker/platform \
         /srv/fast/medallion/cache /srv/fast/medallion/replay-work /srv/fast/medallion/tmp /srv/fast/medallion/indexes \
         /srv/data/medallion /srv/data/gastosia /srv/data/backups; do
  if [ -d "$d" ]; then echo "OK   $d"; else echo "FAIL $d"; fail=1; fi
done

echo "== /srv/fast sobre NVMe =="
root_src=$(findmnt -n -o SOURCE /)
fast_src=$(findmnt -n -o SOURCE --target /srv/fast)
root_disk=$(lsblk -slno NAME,TYPE "$root_src" | awk '$2=="disk"{print $1}' | tail -1)
if [ "$fast_src" = "$root_src" ] && echo "$root_disk" | grep -q "^nvme"; then
  echo "OK   /srv/fast=$fast_src (NVMe, disk=$root_disk)"
else
  echo "FAIL /srv/fast=$fast_src root=$root_src disk=$root_disk"; fail=1
fi

echo "== /srv/data sobre HDD LENOVO_DATA =="
dsrc=$(findmnt -n -o SOURCE /srv/data); dfstype=$(findmnt -n -o FSTYPE /srv/data); duuid=$(findmnt -n -o UUID /srv/data)
disk=$(lsblk -slno NAME,TYPE /dev/sda1 | awk '$2=="disk"{print $1}' | tail -1)
if [ "$dsrc" = "/dev/sda1" ] && [ "$dfstype" = "ext4" ] && \
   [ "$duuid" = "10fff707-60e4-4321-afa0-a3c4704d9e8d" ] && [ "$disk" = "sda" ]; then
  echo "OK   /srv/data=$dsrc $dfstype uuid=$duuid disk=$disk"
else
  echo "FAIL /srv/data=$dsrc $dfstype uuid=$duuid disk=$disk"; fail=1
fi
if [ -f /srv/data/.lenovosrv-data-volume ]; then
  echo "OK   marker=$(cat /srv/data/.lenovosrv-data-volume)"
else
  echo "FAIL marker ausente"; fail=1
fi

echo "== platform-net =="
attached=$(docker network inspect -f '{{len .Containers}}' platform-net 2>/dev/null || echo "-")
if [ "$attached" = "0" ]; then echo "OK   platform-net attached_containers=0"; else echo "FAIL platform-net attached=$attached"; fail=1; fi

echo "== paper-runner intacto =="
pr_id=$(docker inspect -f '{{.Id}}' self-evaluating-trading-agent-paper-runner-1)
pr_img=$(docker inspect -f '{{.Image}}' self-evaluating-trading-agent-paper-runner-1)
pr_st=$(docker inspect -f '{{.State.StartedAt}}' self-evaluating-trading-agent-paper-runner-1)
if [ "$pr_id" = "b061332c35724a2147df3c76acdd8ba4cace12157b958766e2d66cb3f34e22bb" ] && \
   [ "$pr_img" = "sha256:e41718c572e15fbc7ff8d927c820e091aee0acc565ba79dcf97ab1aad8a9d0a0" ] && \
   [ "$pr_st" = "2026-09-19T04:00:04.763010163Z" ]; then
  echo "OK   paper-runner id/image/started sin cambios"
else
  echo "FAIL paper-runner id=$pr_id img=$pr_img started=$pr_st"; fail=1
fi

echo "== productivos sin migración (IDs y StartedAt fijos) =="
expect() {
  local name=$1 id=$2 started=$3
  local gid gst
  gid=$(docker inspect -f '{{.Id}}' "$name"); gst=$(docker inspect -f '{{.State.StartedAt}}' "$name")
  if [ "$gid" = "$id" ] && [ "$gst" = "$started" ]; then echo "OK   $name"; else echo "FAIL $name id=$gid started=$gst"; fail=1; fi
}
expect self-evaluating-trading-agent-postgres-1 0c79b6b5d1cdf9f2cf5a503b0557e0fc0ba3b463e5a0007632399b431b97926d 2026-09-02T01:24:46.267698675Z
expect self-evaluating-trading-agent-grafana-1 b796f67478d7f38394767dc80057809fff5a75df4235bb76dfbbba71cf13630b 2026-09-10T16:35:47.19847038Z
expect self-evaluating-trading-agent-prometheus-1 1431d8e01dd62c59bd630c74f018a53d8c82087e6903a1d2f924b48c01a5a843 2026-09-10T16:35:46.985901731Z
expect gastos-ia-app f0866dba0802afe323af07bab1d2eb3510330e3e7e8d3f9f3c6313f9cc9904fc 2026-09-28T02:53:15.850515764Z
expect gastos-ia-samba f9542a5b0b22ec00350e29b78f8f17ebdad37307b3985a1ba3c463ee17f3e69e 2026-09-28T02:53:15.848610612Z
expect gastos-ia-caddy 612427ee20334e3443d90881b307f9df80977341260a711daae978073aa786bf 2026-09-03T03:43:05.671661606Z

echo "== salud =="
health=$(docker inspect -f '{{.State.Health.Status}}' self-evaluating-trading-agent-postgres-1)
[ "$health" = "healthy" ] && echo "OK   postgres health=$health" || { echo "FAIL postgres health=$health"; fail=1; }
http=$(docker exec gastos-ia-app python -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/', timeout=10).code)")
[ "$http" = "200" ] && echo "OK   gastosia HTTP=$http" || { echo "FAIL gastosia HTTP=$http"; fail=1; }

echo "== cero servicios platform corriendo =="
pc=$(docker ps -a --format '{{.Names}}' | grep -c "^platform-" || true)
[ "$pc" = "0" ] && echo "OK   contenedores platform=0" || { echo "FAIL contenedores platform=$pc"; fail=1; }

if [ "$fail" = "0" ]; then echo "M2_VALIDATE_OK"; else echo "M2_VALIDATE_FAIL"; exit 1; fi

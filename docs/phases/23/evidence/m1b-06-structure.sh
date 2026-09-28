#!/usr/bin/env bash
# M1-B paso 06 — estructura base en /srv/data
set -euo pipefail
for d in medallion gastosia backups; do
  install -d -o administrador -g administrador "/srv/data/$d"
done
ls -la /srv/data
for d in medallion gastosia backups; do test -d "/srv/data/$d" || exit 1; done
test -f /srv/data/.lenovosrv-data-volume
echo "STRUCTURE_OK"

#!/usr/bin/env bash
# M2 paso 02c — normalizar permisos de /srv/fast (755, root:root) tras la creación
set -euo pipefail
chmod 755 /srv/fast
ls -ld /srv/fast /srv/fast/medallion
ls -ld /srv/fast/medallion/cache /srv/fast/medallion/replay-work /srv/fast/medallion/tmp /srv/fast/medallion/indexes
echo "PERM_OK"

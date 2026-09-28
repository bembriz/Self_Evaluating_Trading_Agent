#!/usr/bin/env bash
# M1-B paso 07 — restaurar datos activos de GastosIA desde el backup validado + verificación hash
set -euo pipefail
B=/srv/backup-before-medallion/gastosia
T=/srv/data/gastosia
echo "== origen (backup) =="
ls -la "$B/host/warehouse-GastosIA"
echo "== rsync =="
rsync -a "$B/host/warehouse-GastosIA/" "$T/"
echo "== conteo restaurado =="
FILES=$(find "$T" -type f | wc -l); echo "FILES=$FILES"
BYTES=$(find "$T" -type f -printf '%s\n' | awk '{s+=$1} END{print s}'); echo "BYTES=$BYTES"
echo "== hash verify contra SHA256SUMS del backup =="
cd "$T"
grep -F ' ./host/warehouse-GastosIA/' "$B/SHA256SUMS" | sed 's| ./host/warehouse-GastosIA/| ./|' | sha256sum -c -
echo "RESTORE_HASH_OK"
test "$FILES" -eq 20
test "$BYTES" -eq 597764
echo "RESTORE_OK"

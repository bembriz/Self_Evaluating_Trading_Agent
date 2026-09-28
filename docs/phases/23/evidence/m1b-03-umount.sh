#!/usr/bin/env bash
# M1-B paso 03 — umount /mnt/warehouse (previa verificación de holds)
set -euo pipefail
echo "== holds previos (debe estar vacío) =="
fuser -vm /mnt/warehouse || true
lsof +D /mnt/warehouse 2>/dev/null | head -30 || true
echo "== umount =="
umount /mnt/warehouse
echo "UMOUNT_RC=0"
if findmnt /mnt/warehouse >/dev/null 2>&1; then echo "WAREHOUSE_STILL_MOUNTED"; exit 1; fi
echo "WAREHOUSE_UNMOUNTED_OK"
ls -ld /mnt/warehouse
systemctl reset-failed mnt-warehouse.mount 2>/dev/null || true

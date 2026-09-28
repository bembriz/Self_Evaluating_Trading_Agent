#!/usr/bin/env bash
# M1-B paso 02 — re-verificación de identidad by-id del disco objetivo (solo lectura)
set -euo pipefail
BYID=/dev/disk/by-id/ata-ST1000LM035-1RK172_WDEV3QGR
echo "== by-id =="; ls -l "$BYID"
DEV=$(readlink -f "$BYID"); echo "RESOLVES_TO=$DEV"
MODEL=$(udevadm info --query=property --name="$DEV" | sed -n 's/^ID_MODEL=//p')
SERIAL=$(udevadm info --query=property --name="$DEV" | sed -n 's/^ID_SERIAL_SHORT=//p')
ROTA=$(lsblk -dno ROTA "$DEV" | tr -d ' ')
SIZE=$(lsblk -dno SIZE "$DEV" | tr -d ' ')
echo "MODEL=$MODEL"; echo "SERIAL=$SERIAL"; echo "ROTA=$ROTA"; echo "SIZE=$SIZE"
echo "== mount actual =="
findmnt -n -o SOURCE,TARGET,FSTYPE,UUID /mnt/warehouse
test "$DEV" = "/dev/sda"
test "$MODEL" = "ST1000LM035-1RK1"
test "$SERIAL" = "WDEV3QGR"
test "$ROTA" = "1"
test "$(findmnt -n -o SOURCE /mnt/warehouse)" = "/dev/sda1"
test "$(findmnt -n -o TARGET /mnt/warehouse)" = "/mnt/warehouse"
test "$(findmnt -n -o FSTYPE /mnt/warehouse)" = "ntfs3"
echo "IDENTITY_RECHECK_OK"

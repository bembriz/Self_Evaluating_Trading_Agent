#!/usr/bin/env bash
# M1-B paso 05 — mount /srv/data + fstab por UUID + marker + validación
set -euo pipefail
BYID=/dev/disk/by-id/ata-ST1000LM035-1RK172_WDEV3QGR
PART="${BYID}-part1"
UUID=$(blkid -s UUID -o value "$PART")
echo "NEW_UUID=$UUID"
test -n "$UUID"
echo "== mount =="
mkdir -p /srv/data
mount "$PART" /srv/data
echo "== fstab: comentar línea antigua del warehouse =="
grep -n "warehouse" /etc/fstab
sed -i 's|^UUID=0ADC29B7DC299DC7 |#UUID=0ADC29B7DC299DC7 |' /etc/fstab
echo "== fstab: añadir /srv/data por UUID =="
grep -q "^UUID=$UUID /srv/data" /etc/fstab || printf 'UUID=%s /srv/data ext4 defaults,nofail 0 2\n' "$UUID" >> /etc/fstab
systemctl daemon-reload
echo "== marker =="
printf 'LENOVO_DATA\nuuid=%s\nmounted_at=/srv/data\ncreated=%s\n' "$UUID" "$(date -Iseconds)" > /srv/data/.lenovosrv-data-volume
echo "== validación =="
findmnt -n -o SOURCE,TARGET,FSTYPE,UUID /srv/data
test "$(findmnt -n -o UUID /srv/data)" = "$UUID"
test "$(findmnt -n -o FSTYPE /srv/data)" = "ext4"
test -f /srv/data/.lenovosrv-data-volume
cat /srv/data/.lenovosrv-data-volume
echo "-- fstab relevante --"
grep -E "warehouse|/srv/data" /etc/fstab
if findmnt /mnt/warehouse >/dev/null 2>&1; then echo "WAREHOUSE_STILL_MOUNTED"; exit 1; fi
echo "MOUNT_FSTAB_MARKER_OK"

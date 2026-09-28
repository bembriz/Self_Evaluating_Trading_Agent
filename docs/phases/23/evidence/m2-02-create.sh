#!/usr/bin/env bash
# M2 paso 02 — GUARDS + creación de /srv/docker/platform y /srv/fast/medallion (aborta si guard falla)
set -euo pipefail
UUID_EXPECT=10fff707-60e4-4321-afa0-a3c4704d9e8d

echo "== GUARD 1: /srv/data = source/ext4/UUID =="
src=$(findmnt -n -o SOURCE /srv/data)
fstype=$(findmnt -n -o FSTYPE /srv/data)
uuid=$(findmnt -n -o UUID /srv/data)
echo "source=$src fstype=$fstype uuid=$uuid"
[ "$fstype" = "ext4" ]  || { echo "ABORT: fstype != ext4"; exit 1; }
[ "$uuid" = "$UUID_EXPECT" ] || { echo "ABORT: UUID mismatch"; exit 1; }
[ "$src" = "/dev/sda1" ] || { echo "ABORT: source != /dev/sda1"; exit 1; }
echo "GUARD1_OK"

echo "== GUARD 2: marker =="
test -f /srv/data/.lenovosrv-data-volume || { echo "ABORT: marker ausente"; exit 1; }
echo "marker=$(cat /srv/data/.lenovosrv-data-volume)"
echo "GUARD2_OK"

echo "== GUARD 3: raíz (y por tanto /srv/fast) sobre NVMe =="
root_src=$(findmnt -n -o SOURCE /)
echo "root_src=$root_src"
root_disk=$(lsblk -slno NAME,TYPE "$root_src" | awk '$2=="disk"{print $1}' | tail -1)
echo "root_disk=$root_disk"
echo "$root_disk" | grep -q "^nvme" || { echo "ABORT: disco raíz no es NVMe (root_disk=$root_disk)"; exit 1; }
echo "GUARD3_OK"

echo "== creación =="
mkdir -p /srv/docker/platform
mkdir -p /srv/fast/medallion/cache /srv/fast/medallion/replay-work /srv/fast/medallion/tmp /srv/fast/medallion/indexes
chown administrador:administrador /srv/docker/platform /srv/fast/medallion
chown administrador:administrador /srv/fast/medallion/cache /srv/fast/medallion/replay-work /srv/fast/medallion/tmp /srv/fast/medallion/indexes
chmod 755 /srv/docker/platform /srv/fast/medallion /srv/fast/medallion/cache /srv/fast/medallion/replay-work /srv/fast/medallion/tmp /srv/fast/medallion/indexes
ls -la /srv/docker/platform
ls -la /srv/fast/medallion
echo "M2_CREATE_OK"

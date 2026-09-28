#!/usr/bin/env bash
# M1-B paso 04 — GPT + una partición + ext4 + label LENOVO_DATA (DESTRUCTIVO, autorizado por gate M1-B)
set -euo pipefail
BYID=/dev/disk/by-id/ata-ST1000LM035-1RK172_WDEV3QGR
PART="${BYID}-part1"
echo "== re-identificación final antes de destruir =="
ls -l "$BYID"
test "$(readlink -f "$BYID")" = "/dev/sda"
test "$(udevadm info --query=property --name=/dev/sda | sed -n 's/^ID_SERIAL_SHORT=//p')" = "WDEV3QGR"
test "$(lsblk -dno MODEL /dev/sda | tr -d ' ')" = "ST1000LM035-1RK1"
echo "FINAL_IDENTITY_OK (by-id, no solo /dev/sda)"
echo "== mklabel gpt =="
parted -s "$BYID" mklabel gpt
echo "== mkpart ext4 1MiB-100% =="
parted -s "$BYID" mkpart primary ext4 1MiB 100%
partprobe "$BYID" 2>/dev/null || true
udevadm settle
test -e "$PART"
echo "== mkfs.ext4 -L LENOVO_DATA =="
mkfs.ext4 -L LENOVO_DATA -F "$PART"
echo "== post-format =="
lsblk -no NAME,TYPE,FSTYPE,LABEL,SIZE "$BYID"
blkid "$PART"
tune2fs -l "$PART" | grep -E "Filesystem volume name|Filesystem UUID|Block count" | head -5
echo "FORMAT_OK"

#!/usr/bin/env bash
# M1-C paso 01 — actualizar plantilla repo/deployment/docker/compose.yaml (NO desplegar)
set -euo pipefail
R=/srv/docker/gastos-ia/repo
F="$R/deployment/docker/compose.yaml"
echo "== antes: refs activas =="
grep -n "/mnt/warehouse/GastosIA" "$F" || echo NO_REFS_BEFORE
echo "== backup =="
OWN=$(stat -c '%u:%g' "$F")
cp -a "$F" "$F.bak-m1c"
echo "OWN_BEFORE=$OWN"
echo "== sed =="
sed -i 's|/mnt/warehouse/GastosIA|/srv/data/gastosia|g' "$F"
OWN_AFTER=$(stat -c '%u:%g' "$F")
if [ "$OWN" != "$OWN_AFTER" ]; then echo "RESTORE_OWNERSHIP $OWN_AFTER -> $OWN"; chown "$OWN" "$F"; fi
stat -c '%n %U:%G %a' "$F" "$F.bak-m1c"
echo "== nuevas refs =="
grep -n "/srv/data/gastosia" "$F"
echo "== refs activas restantes en repo (excluye .git/.bak) =="
grep -rn "/mnt/warehouse/GastosIA" "$R" --exclude-dir=.git --exclude="*.bak-m1c" --exclude="*.bak-m1b" || echo ZERO_ACTIVE_REFS
echo "== estado git del repo (solo lectura) =="
git -C "$R" rev-parse --abbrev-ref HEAD 2>/dev/null || echo NOT_GIT_REPO
git -C "$R" status --porcelain 2>/dev/null | head -10 || true
echo "TEMPLATE_UPDATED_OK"

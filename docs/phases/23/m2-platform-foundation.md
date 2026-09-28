# M2 — Shared Platform Foundation

**Fecha:** 2026-09-27 (UTC-6) / 2026-09-28 (UTC en lenovosrv)
**Rama:** `medalion` @ `47317b5d4187062461d84dbb354bba820d6e1ac9` (precondición verificada)
**Alcance:** crear base de plataforma compartida en lenovosrv **sin migrar servicios productivos**.
**Gate:** instrucción directa del usuario (M2). Restricciones: NO commit, NO push, NO migración de servicios.

## Ejecución (evidencia en `docs/phases/23/evidence/`)

| Paso | Artefacto | Resultado |
|---|---|---|
| 01 preflight | `m2-01-preflight.log` | exit=1 — sintaxis `findmnt ... TARGET /` inválida (corregido en 01b) |
| 01b preflight | `m2-01b-preflight.log` | PASS — sda HDD + nvme0n1; `/srv/data` sda1/ext4/UUID OK; marker `LENOVO_DATA`; `/srv/fast`, `/srv/docker/platform` y `platform-net` ABSENTES (esperado); baseline de contenedores registrado; postgres healthy; GastosIA HTTP 200 |
| 02 guards + creación | `m2-02-create.log` | exit=1 — **ABORT correcto del GUARD 3**: `lsblk -s` con árbol (`├──`) rompía `grep ^nvme`; nada creado |
| 02b guards + creación | `m2-02b-create.log` | PASS — GUARD1 (sda1/ext4/UUID), GUARD2 (marker), GUARD3 (`root_disk=nvme0n1`); creados `/srv/docker/platform` y `/srv/fast/medallion/{cache,replay-work,tmp,indexes}` (propiedad `administrador`) |
| 02c permisos | `m2-02c-srv-fast-perm.log` | exit=1 — quoting roto en el one-liner (no ejecutó nada) |
| 02c permisos (retry) | `m2-02c-perm.log` | PASS — `/srv/fast` 755 |
| 03 red | `m2-03-network.log` | PASS — `platform-net` creada (`9fc54c67f7ef…`, bridge, **attached_containers=0**) |
| 04 validación | `m2-04-validate.log` | exit=1 — `findmnt /srv/fast` sin `--target` (no es mountpoint) falla bajo `set -e` |
| 04b validación | `m2-04b-validate.log` | **PASS — todos los checks OK** |
| 05 repo compose | `m2-05-repo-compose.log` | PASS — `docker compose config -q` OK; servicios inertes tras `profiles` (lista vacía sin perfil); local sin daemon docker (no necesario: `config` es solo cliente) |
| 06 ledger tests | `m2-06-ledger-tests.log` | PASS (39 tests) — valida el `mark-done` de `23/m2-platform` |

> Los intentos fallidos (01, 02, 02c-one-liner, 04) quedan registrados a propósito: los GUARDS abortaron antes de crear nada y cada fallo se corrigió sin tocar servicios productivos.

## Estado final verificado (`m2-04b`)

- `/srv/docker/platform/` — creado (administrador, 755)
- `/srv/fast/medallion/{cache,replay-work,tmp,indexes}` — creados (administrador, 755); `/srv/fast` = root LVM sobre **`nvme0n1`** (NVMe) ✓
- `/srv/data` — `/dev/sda1` ext4 UUID `10fff707-60e4-4321-afa0-a3c4704d9e8d` sobre **`sda`** (HDD) ✓; marker `LENOVO_DATA` ✓; `medallion/`, `gastosia/`, `backups/` presentes ✓
- `platform-net` — externa, bridge, **0 contenedores conectados** ✓
- **Cero migraciones:** postgres `0c79b6b5…`, grafana `b796f674…`, prometheus `1431d8e0…`, caddy `612427ee…`, gastos-ia-app/samba — IDs y `StartedAt` idénticos al baseline de M1-C; contenedores `platform-*` = 0
- paper-runner — ID `b061332c3572…`, ImageID `sha256:e41718c572e1…`, StartedAt `2026-09-19T04:00:04.763010163Z` — **intocado**
- Salud: postgres `healthy`, GastosIA `HTTP 200`

## Repo (sin levantar nada)

- `deployment/platform/compose.yaml` — compose base con `platform-postgres` bajo `profiles: ["platform"]` (inerte sin perfil) y red externa `platform-net`; password por env var, sin secretos en repo
- `deployment/platform/README.md` — documentación de `platform-net`, tiers de storage y reglas de migración (gate obligatorio)
- `docker compose -f deployment/platform/compose.yaml config -q` → PASS

## Condiciones de la regla M2 (post-ejecución)

1. `/srv/fast` sobre NVMe — PASS
2. `/srv/data` sobre HDD + marker/UUID validados con abort si no coinciden — PASS
3. `platform-net` existe, sin contenedores — PASS
4. Cero migraciones / cero reinicios productivos — PASS (IDs+StartedAt fijos)
5. Evidencia + doc creadas — PASS
6. `progress.py mark-done 23/m2-platform` — PASS (tests del ledger en verde)

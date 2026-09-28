# M1-B — Reformato del HDD a ext4 LENOVO_DATA + Restore de GastosIA

**Fecha:** 2026-09-27 (UTC-6) / 2026-09-28 (UTC en lenovosrv)
**Gate:** aprobado explícitamente por el usuario ("APRUEBO M1-B") tras M1-A PASS
**Regla global:** `~/.config/opencode/AGENTS.md` §LENOVOSRV — condiciones 1–5 verificadas en M1-A, condición 6 satisfecha con esta aprobación

## Autorización

El usuario autorizó expresamente: formatear `/dev/disk/by-id/ata-ST1000LM035-1RK172_WDEV3QGR`, destruir el contenido de `/mnt/warehouse`, crear ext4 `LENOVO_DATA` montado en `/srv/data` y restaurar GastosIA desde el backup validado.

## Ejecución (evidencia en `docs/phases/23/evidence/`)

| Paso | Artefacto | Resultado |
|---|---|---|
| 00 precondiciones (compose, ownership, caddy) | `m1b-00-preconditions.log` | PASS (dir compose root-only) |
| 00b escaneo root del compose | `m1b-00b-root-scan.log` | PASS (binds en líneas 14/48 de `compose.yaml`; caddy usa DNS `app:8000`) |
| 01 detener solo binds activos | `m1b-01-stop-binds.log` | PASS (`gastos-ia-app`, `gastos-ia-samba` parados; caddy sin bind sigue Up) |
| 02 re-verificación by-id | `m1b-02-identity.log` | PASS (ST1000LM035-1RK1 / WDEV3QGR / 931,5G / HDD / sda1 ntfs3 en `/mnt/warehouse`) |
| 03 umount | `m1b-03-umount.log` | PASS (sin holds; warehouse desmontado) |
| 04 GPT + 1 partición + ext4 + label | `m1b-04-format.log` | PASS (identidad final re-verificada antes de destruir; UUID `10fff707-60e4-4321-afa0-a3c4704d9e8d`) |
| 05 mount + fstab por UUID + marker | `m1b-05-mount-fstab.log` | PASS (línea warehouse comentada; marker `.lenovosrv-data-volume` creado) |
| 06 estructura base | `m1b-06-structure.log` | PASS (`medallion`, `gastosia`, `backups` — propiedad administrador) |
| 07 restore GastosIA | `m1b-07-restore.log` | PASS (20 archivos / 597 764 bytes / 20/20 hashes OK) |
| 08 adaptar binds + recreate | `m1b-08-compose-adapt.log` | PASS (`compose.yaml.bak-m1b` respaldado; binds → `/srv/data/gastosia`; caddy sin recreate) |
| 09 validación | `m1b-09-validate.log` | PASS |
| 10 comprobación final | `m1b-10-final-check.log` | PASS (samba healthy, restarts=0, lsblk = ext4 LENOVO_DATA) |

> Nota: `m1b-00-preconditions.log` tiene `exit=0` pero su sección de ownership falló por permisos (dir root-only); el escaneo real se hizo en `m1b-00b` con sudo. `dbg-oneshot.log` / `dbg-sudo-path.log` registran la depuración del mecanismo sudo (patrón final: un solo `sudo -S bash -s`, sin `sudo -v`/`-n`).

## Estado final verificado

- `/srv/data` = `/dev/sda1` ext4, UUID `10fff707-60e4-4321-afa0-a3c4704d9e8d`, label `LENOVO_DATA` (916 GiB libres)
- fstab: línea antigua del warehouse comentada; nueva entrada por UUID con `nofail`
- Marker: `/srv/data/.lenovosrv-data-volume`
- `/mnt/warehouse` ya NO montado (directorio vacío residual)
- GastosIA: app `HTTP 200`, `expense_records=636`, samba `healthy` en :445/:139, datos restaurados legibles desde `/data/gastos` y `/shares/gastos`
- paper-runner: mismo ID `b061332c3572…`, ImageID `sha256:e41718c572e1…`, StartedAt `2026-09-19T04:00:04.763010163Z` — intocado; binds solo sobre `/srv/docker/self-evaluating-trading-agent/{reports,certification,safeguard}`
- SETA: grafana `b796f67478d7…`, prometheus `1431d8e01dd6…`, postgres `0c79b6b5d1cd…` — IDs y StartedAt sin cambios
- Backup GastosIA sigue en `/srv/backup-before-medallion/gastosia` sobre el NVMe raíz (no en el disco reformateado)

## Contenido destruido (según autorización)

Todo el contenido previo de `/mnt/warehouse` que no pertenece a GastosIA: Hyper-V (VM legada), `PostgreSQL` legado, datos personales, `$RECYCLE.BIN`, etc. Solo se restauró el árbol activo GastosIA (20 archivos) verificado por hash contra `SHA256SUMS`.

## M1-C — Alineación de repos con el storage nuevo (post-M1-B)

Solo plantillas/repos, sin deploy ni commit:

| Paso | Artefacto | Resultado |
|---|---|---|
| 01 actualizar plantilla server | `m1c-01-template-update.log` | PASS (2 binds → `/srv/data/gastosia`; backup `.bak-m1c` con ownership `administrador` preservado; `ZERO_ACTIVE_REFS`) |
| 02 compose config (sin `.env`) | `m1c-02-compose-config.log` | PASS fallback `--no-interpolate` (falta `.env` de despliegue en el repo — esperable) |
| 02b compose config PLENO | `m1c-02b-compose-config-full.log` | PASS (`docker compose config -q` exit 0 con enlace `.env` transitorio, limpiado en la misma ejecución; binds resueltos → `/srv/data/gastosia`) |
| 03 prod sin cambios | `m1c-03-prod-unchanged.log` | PASS (GastosIA sin recreate/restarts; paper-runner, SETA core, HTTP 200 intactos) |
| 04 lint | `m1c-04-ruff-check.log`, `m1c-04b-ruff-format.log` | PASS / PASS |
| 05 harness tests | `m1c-05-harness-tests.log`, `m1c-05b-…-without-pdf.log` | exit=1 pre-existente (`test_gen_pdf` requiere dev-deps `markdown`/`weasyprint` sin DP) / PASS sin `test_gen_pdf` |
| 06 producto | `m1c-06-product-tests.log`, `m1c-06b-product-unit-tests.log` | exit=1 solo integration (PG :5433 caído, pre-existente) / PASS unitario |

- Compose **activo** NO se tocó (sigue el `.bak-m1b` de M1-B, binds ya en `/srv/data`).
- `GastoBot` local (`deployment/docker/compose.yaml`, branch `dev`) también tiene 2 refs stale — fuera de alcance de M1, solo reporte.

## Observaciones / deuda

1. ~~**Plantilla no activa desactualizada**~~ — resuelta en M1-C: `/srv/docker/gastos-ia/repo/deployment/docker/compose.yaml` actualizada a `/srv/data/gastosia` (validada con `docker compose config`); **no desplegada**.
2. Credencial sudo histórica detectada en evidencia ya versionada. Rotación requerida y limpieza de historial pendiente en gate separado.
3. El directorio `/mnt/warehouse` queda vacío; la línea fstab quedó comentada (reversible).
4. No se ejecutó ningún commit (pendiente de autorización).

## Condiciones de la regla global M1 (post-ejecución)

1. Backup verificado — PASS (SHA256SUMS 5234/5234)
2. Restore test PASS — PASS (M0-II + restore real M1-B con hashes OK)
3. Identidad by-id — PASS (verificada en M1-A, paso 02 y de nuevo antes del mkfs)
4. Dispositivo objetivo coincide — PASS
5. Certificación SETA intacta — PASS (IDs/StartedAt/binds sin cambios)
6. Aprobación humana explícita — PASS (gate M1-B)

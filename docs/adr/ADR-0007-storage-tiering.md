# ADR-0007 — Tiering de almacenamiento: NVMe para HOT, SATA HDD para canónico/COLD

**Fecha:** 2026-09-24
**Estado:** proposed (gate M0)

## Contexto

lenovosrv tiene dos discos con roles distintos por naturaleza: NVMe Samsung 970 EVO 500GB (raíz/LVM, Docker root, ~417 GB libres medidos) de baja latencia, y SATA Seagate ST1000LM035 1TB (`/dev/disk/by-id/ata-ST1000LM035-1RK172_WDEV3QGR`, hoy NTFS `Warehouse` en `/mnt/warehouse`, 489 GB usados) de capacidad pero alta latencia. Medallion generará Bronce de trades masivo (órdenes de magnitud por encima de las velas) más Silver/Gold y working sets de replay; sin política explícita, los replays pueden llenar la raíz NVMe y tumbar Docker/PostgreSQL. Además, la única copia operativa de los datos masivos debe sobrevivir a la borrado de cualquier caché.

## Decisión

**Dos tiers con autoridad asimétrica (ADR-0007 = §14–§16 del diseño Medallion):**

- **HOT/WARM → NVMe** (`/`, `/srv/docker`, `/srv/fast/medallion/{cache,replay-work,tmp,indexes}`): Postgres activo, estado de app, working set de replay, transformaciones temporales, índices y experimentos — latencia-sensitive.
- **COLD/canónico → SATA HDD futuro `/srv/data` ext4, label `LENOVO_DATA`, fstab por UUID, marker fail-closed `/srv/data/.lenovosrv-data-volume`**: Bronze inmutable, Silver histórico, Gold, logs, recibos, backups. **El HDD es el almacén autoritativo persistente.**
- **La caché NVMe es desechable y reproducible:** borrar `/srv/fast/medallion` nunca destruye datos canónicos.
- **Safeguards de capacidad en NVMe:** `SSD_MIN_FREE_GB = max(50 GB, 10%×total)` (=50 GB hoy) con **fail-closed** (aborta si libre < umbral); `SSD_CACHE_MAX_GB = min(config, 20%×total, libre − SSD_MIN_FREE_GB)` (techo medido hoy 91 GB; config inicial propuesta 64 GB), re-derivable por medición en cada gate; limpieza solo de árboles reproducibles; jamás auto-borrar canónicos/Docker/Postgres.
- Identidad física **siempre** por `/dev/disk/by-id/…`, nunca `/dev/sda` a secas.

## Alternativas consideradas

| Opción | Consecuencias si se elige |
|---|---|
| Todo en NVMe (un solo disco) | La raíz (455G) no absorbe Bronce+Silver+backups a medio plazo; un replay mal dimensionado llena `/` y tumba Docker/PG (riesgo operativo directo) |
| Todo en HDD (sin caché NVMe) | Replay e ingestas multi-hora por latencia mecánica; rendimiento inaceptable para working sets |
| ZFS/btrfs con RAID o compresión | Capas potentes pero complejidad y memoria adicionales; el hardware es 1 HDD simple + 1 NVMe; ext4 cumple con menos moving parts (complejidad mínima) |
| Caché NVMe sin cuota ni fail-closed | El fallo previsible es llenar la raíz; sin umbral mínimo de libre, el estallido es ciego |
| Borrar automáticamente "lo que haga falta" para liberar espacio | Riesgo de auto-destrucción de canónicos/Docker/PG; se prohíbe: solo caché reproducible |

## Consecuencias

### Positivas

- Latencia donde importa (replay, índices, Postgres) y capacidad donde es barata (Bronce/Silver/backups); el crecimiento de Medallion no compite con el sistema.
- Garantía estructural: borrado de caché ⇒ reconstruible desde canónico (HDD), jamás pérdida de datos.
- Fail-closed: los umbrales impiden que un pipeline degraden el servicio base; valores derivados de medición real, re-calificables por gate.

### Negativas / trade-offs aceptados

- Formato del HDD = operación destructiva que exige backup de GastosIA + test de restore + `DISK_IDENTITY_MATCH` + USER GATE (gate M1; NO en M0).
- Staging HDD→NVMe añade una fase de copia en el pipeline de replay (mitigable con particiones seleccionadas).
- NTFS actual implica conversión: nada de datos personales del warehouse entra en el plan de Medallion salvo GastosIA (decisión del usuario, §26 del diseño).

### Neutras

- El mount actual `/mnt/warehouse` y el futuro `/srv/data` conviven hasta M1; fstab futuro solo por UUID con `nofail`.
- `SSD_MIN_FREE_GB`/`SSD_CACHE_MAX_GB` se re-miden en cada gate M* y se registran como evidencia.

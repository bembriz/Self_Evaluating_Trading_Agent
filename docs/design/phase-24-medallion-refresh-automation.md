# Fase 24 — Propuesta de diseño: Refresh diario automatizado del pipeline Medallion

**Fecha:** 2026-09-29 · **Base:** `main` @ `a06ad1e85ec9729c32c6659261ee078d2acd47cc`
**Estado:** diseño aprobado para bootstrap (NO implementada). No modifica `progress.yaml` ni
`splits/v1.json` directamente; el registro de fase se hace solo mediante `progress.py`.
**Referencias:** `docs/design/medallion-replay-architecture.md`, ADR-0005/0006/0007/0008,
skill `medallion-market-data`, `.opencode/skills/backtesting`, skill `infra-control`.

---

## 1. Objetivo

Automatizar de forma **diaria, incremental e idempotente** la cadena
`Bybit → Bronze → Silver trades → Silver candles` en lenovosrv, mediante
**systemd timer** (sin Airflow/Kafka, sin daemon Python permanente), descargando **solo
los días faltantes**, con `.part → validate/hash → rename atómico`, guards de marker/UUID/
espacio libre y failsafe total sobre splits/paper.

La automatización distingue dos dominios separados:

1. **Evaluación congelada:** `DEVELOPMENT`, `WALK_FORWARD` y `FINAL_HOLDOUT` definidos
   por `splits/v1.json`. Estos splits no se recalculan, no se extienden y no se modifican
   en esta fase.
2. **Colección futura no asignada:** fechas posteriores al final del holdout. Bronze y
   Silver pueden recolectarlas para no perder continuidad operativa, pero no entran a Gold
   de evaluación, research, replay ni tuning sin gate humano explícito.

## 2. Estado actual (lo que ya existe, reutilizable)

| Elemento | Estado | Ubicación |
|---|---|---|
| Bronze idempotente + split guard + `.part`/hash/rename | ✅ implementado | `src/infrastructure/medallion/bronze.py:326` (`download_day`), `split_guard.py` |
| Silver trades / candles deterministas | ✅ | `silver.py`, `candles.py` |
| Gold inmutable (dataset_id por identidad, skip, conflict ⇒ FAIL) | ✅ | `gold.py:131,348` |
| CLIs por capa | ✅ | `cli.py`, `silver_cli.py`, `candles_cli.py`, `gold_cli.py` |
| Imagen one-shot aislada + compose | ✅ (M8) | `deployment/medallion/` |
| Marker guard (`ensure_marker`) | ✅ | `bronze.py:214` |
| **Guard de espacio libre `SSD_MIN_FREE_GB` / cuota `SSD_CACHE_MAX_GB`** | ❌ **falta** (solo diseño) | spec en skill + arquitectura §26 |
| **Detección de días faltantes / refresco incremental** | ❌ falta | — |
| **systemd service+timer, retries, status, retención** | ❌ falta | — |

## 3. Restricción crítica: splits de evaluación congelados

`splits/v1.json` define tres splits de evaluación inmutables para `SPLIT_VERSION=1`:

| Split | Rango congelado en `splits/v1.json` | Uso automático permitido |
|---|---|---|
| `DEVELOPMENT` | `2023-09-08T17:45:00Z` → `2025-06-17T17:30:00Z` | Sí, para desarrollo/backfill autorizado |
| `WALK_FORWARD` | `2025-06-17T17:45:00Z` → `2026-03-14T17:30:00Z` | No en Phase 24; reads automáticos = 0 |
| `FINAL_HOLDOUT` | `2026-03-14T17:45:00Z` → `2026-08-23T17:30:00Z` | No en Phase 24; reads automáticos = 0 |

La Phase 24 **no modifica** este archivo ni transforma datos entre splits. La política de
evaluación sigue siendo fail-closed: `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0` y
`HOLDOUT_STATE=PRISTINE` para research/replay/tuning automáticos.

## 3.1 Future collection / unassigned

Las fechas posteriores a `FINAL_HOLDOUT.last_timestamp` pertenecen a una zona operacional
separada: **`FUTURE_COLLECTION` / `UNASSIGNED`**.

Propiedades obligatorias:

1. **Bronze puede descargarla** desde Bybit con la misma política inmutable, hash y rename
   atómico que el histórico congelado.
2. **Silver trades/candles puede derivarla** para continuidad, validación técnica y futura
   promoción.
3. **Gold de evaluación no la incluye automáticamente.** Un dataset Gold usado por replay,
   investigación, tuning, paper certification o comparaciones oficiales debe referenciar solo
   splits congelados aprobados.
4. **Research access fail-closed:** CLIs/notebooks/jobs de research deben requerir un
   `dataset_id` Gold aprobado; no pueden descubrir ni leer `UNASSIGNED` por fecha/ruta por
   defecto.
5. **Promoción a Gold/evaluación requiere gate humano:** crear un nuevo split/versionado,
   asignar rangos, actualizar políticas de acceso y aprobar explícitamente el nuevo dataset.

Consecuencia de diseño: el refresh diario **sí es útil después del holdout**, porque mantiene
Bronze/Silver al día en `FUTURE_COLLECTION`, pero no contamina la evaluación congelada.

## 4. Arquitectura propuesta

```text
systemd timer (diario)  →  systemd service (oneshot)
                               │
                               ▼
                     medallion_refresh  (orquestador stdlib, un proceso efímero)
                        1. preflight/guards (marker, UUID/mount, espacio, split, red)
                        2. plan  → días faltantes por capa y clase de acceso
                        3. run   → por capa y por día: CLI correspondiente (idempotente)
                        4. status→ status.json + resumen a journald
                       5. exit   → 0 OK/no-op · !=0 FAIL (fail closed)
                               │
                               ▼
          contenedor one-shot seta-medallion:<sha>  (reutiliza M8; sin daemon)
```

- **Sin daemon:** el service es `Type=oneshot`; el contenedor es `--rm` (patrón M8).
- **Orquestador en Python stdlib** (`harness/scripts/medallion_refresh.py` o
   `src/infrastructure/medallion/refresh.py` + CLI `refresh_cli`). Reutiliza las funciones
   ya existentes (`download_days`, `transform_days`, `create_dataset`) — **no duplica lógica**.
- **Planner con clases de acceso:** cada día planificado queda clasificado como
  `DEVELOPMENT`, `WALK_FORWARD`, `FINAL_HOLDOUT` o `FUTURE_COLLECTION/UNASSIGNED` antes de
  tocar red o disco. La clase controla qué capas pueden ejecutarse.
- **Contenedor** para aislamiento de ejecución (mismo patrón M8: `network_mode: none` en
  transform, `read_only`, `cap_drop`, mounts `ro` canónico + `rw` scratch). Bronze necesita
  red; se define un **perfil Bronze** con `--network` hacia `public.bybit.com` (allowlist),
  sin credenciales, y un **perfil transform** sin red.

## 5. Definiciones solicitadas

### 5.1 Frecuencia y horario
- **Diario**, `OnCalendar=*-*-* 06:20:00 UTC` (posterior a la publicación de archivos
  diarios de Bybit; ventana de baja carga). `Persistent=true` para recuperar una corrida
  perdida por host apagado. `RandomizedDelaySec=15m` para evitar picos.

### 5.2 Detección de días faltantes
- **Fuente de verdad:** `manifest.json` de cada capa.
- `target = hoy − 1 día (UTC)`; `start = DEVELOPMENT_FIRST_DAY` o `last_complete_day + 1`
  para incremental.
- El planner clasifica cada día:
  - `DEVELOPMENT`: Bronze/Silver/Candles permitidos; Gold solo si el dataset aprobado lo
    requiere.
  - `WALK_FORWARD` y `FINAL_HOLDOUT`: lectura/escritura automática bloqueada en Phase 24,
    salvo un job explícito de auditoría aprobado por gate humano.
  - `FUTURE_COLLECTION/UNASSIGNED`: Bronze/Silver/Candles permitidos; Gold/evaluación
    bloqueados por defecto.
- `missing_bronze = [start..target] − {días presentes en manifest Bronze con hash válido}`,
  filtrado por clase de acceso permitida para Bronze.
- `missing_silver/candles` se derivan de sus manifests y de Bronze válido, filtrado por clase
  de acceso permitida para Silver.
- `missing_gold` se calcula únicamente sobre datasets Gold explícitamente aprobados; nunca por
  descubrimiento automático de días `UNASSIGNED`.
- El planner **solo lee manifests/hashes** (no re-descarga) ⇒ verificación sin duplicar.

### 5.3 Comportamiento ante fallo parcial
- El job avanza **capa por capa** y **día por día**; cada unidad es idempotente.
- Si una capa falla: **se detiene la cadena** (no se construye Silver/Gold con Bronze
  incompleto) y la corrida termina `FAILED_PARTIAL` con `failed_layer`/`failed_day`.
- Los días ya completados quedan persistidos (reanudable); la siguiente corrida retoma.
- Gold **nunca** se reescribe: un dataset existente con contenido distinto ⇒ `DatasetConflictError`
  (FAIL CLOSED, ya implementado en `gold.py`).

### 5.4 Política de retries
- **Reintentos acotados por día** en el orquestador (p. ej. 3 intentos, backoff
  exponencial 30s/2m/8m) ante errores de red; **no** ante guards (split/marker/hash ⇒ fail
  inmediato, no reintentable).
- `systemd`: `Restart=on-failure` a nivel de service con `RestartSec=5m` y
  `StartLimitBurst=2` (evita bucles); el timer reintenta la corrida al día siguiente.
- Idempotencia garantiza que reintentar nunca duplica.

### 5.5 Retención de logs/cache
- **Logs por corrida:** `docs/phases/24/evidence/refresh-YYYYMMDDTHHMMSSZ.log` +
  `status.json`; retención **N=30 días** (rotación por el propio orquestador/job
  `logrotate` de systemd journal). Journald conserva los últimos 30 días.
- **Caché NVMe `/srv/fast/medallion/**`:** desechable; purga de árboles reproducibles
  (staging, `.part` huérfanos, outputs de verificación) al superar `SSD_CACHE_MAX_GB`.
- **Canónico HDD `/srv/data`:** nunca se purga automáticamente (inmutable).

### 5.6 Health / status sencillo
- `status.json` atómico (`.part` + rename) con: `last_run_utc`, `result`
  (`OK|OK_NOOP|ACCESS_BLOCKED|FAILED_PARTIAL|FAILED_GUARD`), `missing_days`,
  `downloaded/transformed/created/skipped`, `last_gold_dataset_id`, `free_gb`,
  `layer_timings`.
- CLI `refresh status [--json]` que imprime el estado (sin daemon).
- Opcional: exporter de texto Prometheus (`.prom`) consumido por el Prometheus existente
  — **sin** nuevos servicios.

### 5.7 Cómo crear nuevas versiones Gold
- Gold es **inmutable**: cada materialización con identidad nueva (nuevo día, nueva
  versión de transformador, nuevo `execution_model`) produce un **nuevo `dataset_id`**
  (`gold.compute_dataset_id`) en un directorio nuevo `gold/replay-datasets/<symbol>/<id>/`.
- El refresh **no** versiona Gold a mano: el `dataset_id` se deriva de la identidad de
  entradas/versiones. Un mismo conjunto ⇒ `skipped`; conflicto ⇒ fail closed.
- **Retención Gold:** política explícita (p. ej. conservar el último y N anteriores;
   nunca borrar el referenciado por replay/paper). Fuera de alcance: borrado automático
   en esta fase (solo se documenta el criterio).
- **Promoción desde `UNASSIGNED`:** fuera del refresh automático. Requiere reporte de
  candidatos, revisión humana, nuevo split/versionado o dataset policy aprobada, y ejecución
  manual/auditada de Gold.

### 5.8 Verificación del job sin duplicar datos
- Modo **`plan`/`--dry-run`**: calcula días faltantes y hashes y **no escribe nada**
  (solo lectura de manifests).
- **Re-ejecución idempotente**: segunda corrida ⇒ todo `SKIP` (`downloaded=0`,
  `transformed=0`, `created=0`) y `OK_NOOP`.
- Comprobación de integridad: recomputar sha256 de particiones referenciadas por Gold vs
  manifest (ya exigido por el replay). Cualquier divergencia ⇒ FAIL.

## 6. Guards / fail-closed (todos obligatorios en preflight)

| Guard | Comportamiento |
|---|---|
| Marker `/srv/data/.lenovosrv-data-volume` = `LENOVO_DATA` | ausente/corrupto ⇒ FAIL antes de escribir |
| Identidad de volumen/UUID vs `fstab`/`blkid` | mismatch ⇒ FAIL (nunca `/dev/sda` a secas) |
| Clasificación de acceso por día | `WALK_FORWARD`/`FINAL_HOLDOUT` bloqueados; `UNASSIGNED` solo Bronze/Silver |
| `SSD_MIN_FREE_GB` (50 GB, fail-closed) | espacio insuficiente ⇒ FAIL sin escribir |
| `SSD_CACHE_MAX_GB` (64 GB) | cuota de caché; purga reproducible |
| Red (perfil Bronze) | allowlist `public.bybit.com`; sin credenciales; transform sin red |
| Sin secretos | contenedor sin `.env`/tokens |
| `WALK_FORWARD_READS=0` / `FINAL_HOLDOUT_READS=0` | variables declarativas + sin rutas de WF/holdout |
| `UNASSIGNED_RESEARCH_READS=0` | research/replay/tuning no leen futuro sin Gold aprobado |

## 7. No-impacto

- **Paper/certificación:** el job no toca `/srv/docker/self-evaluating-trading-agent`, no
  reinicia/mueve contenedores de paper; verificación post-run (ID/StartedAt sin cambios).
- **WF/HOLDOUT:** el split guard impide cualquier lectura automática; `HOLDOUT_STATE=PRISTINE`.
- **FUTURE_COLLECTION:** el job puede mantener Bronze/Silver al día, pero esos datos no son
  visibles para research/replay/tuning ni se promocionan a Gold/evaluación automáticamente.
- **Sin ejecución de estrategias:** el refresh termina en datos Medallion autorizados
  (Bronze/Silver/Candles y Gold solo cuando esté aprobado); **no** corre replay ni decisiones.

## 8. Deliverables propuestos (5)

| ID | Entregable | Contenido |
|---|---|---|
| `p24-design` | Diseño + ADR-0008 + Dependency Proposal (si aplica) | este documento + ADR de automatización (systemd, no daemon) |
| `p24-refresh-orchestrator` | Orquestador `refresh` (stdlib) + planner + guards + `plan/status` | detección de faltantes, clases de acceso, fail-closed, reanudable, dry-run |
| `p24-systemd-units` | `medallion-refresh.service` + `.timer` + install/rollback | usuario no privilegiado, sandbox, sin daemon |
| `p24-capacity-guards` | Guards `SSD_MIN_FREE_GB`/`SSD_CACHE_MAX_GB` + retención | purga reproducible; cuota; logs N=30d |
| `p24-tests-uat` | Unit + integration + UAT en lenovosrv | no-duplicación, fail-closed, guards, marker negativo, paper intacto |

## 9. Riesgos y decisiones abiertas (para tu aprobación)

1. **Splits congelados:** ¿confirmas que `DEVELOPMENT`, `WALK_FORWARD` y `FINAL_HOLDOUT`
   permanecen exactamente como `splits/v1.json` y que la Phase 24 no los modifica?
   (recomendado: sí).
2. **Horario:** 06:20 UTC diario con `Persistent=true` — ¿ok?
3. **Retención:** logs 30 días, caché 64 GB, Gold sin borrado automático — ¿ok?
4. **Ubicación de unidades:** `/etc/systemd/system/` ejecutando como `administrador`
   (grupo docker), con `sudo` solo para instalar — ¿ok?
5. **Orquestador:** ¿en `src/infrastructure/medallion/` (probado, cubierto) o en
    `harness/scripts/` (operativo)? Recomendado: lógica en `src/…`, wrapper `.sh` mínimo.
6. **Future collection:** ¿confirmas que Bronze/Silver pueden recolectar fechas posteriores
   al holdout como `UNASSIGNED`, pero Gold/evaluación/research requieren gate humano?
   (recomendado: sí).

## 10. Criterios de aprobación

- `simplify`/`brainstorming` cerrados y decisiones §9 resueltas.
- Dependency Proposal: **ninguna dependencia nueva** (stdlib + systemd + imagen ya existente).
- Confirmación explícita de no-impacto en paper/certificación ni WF/holdout.
- Confirmación explícita de que `FUTURE_COLLECTION/UNASSIGNED` no es un split de evaluación
  y no queda disponible para research/replay/tuning por defecto.
- Registro de la fase 24 vía `progress.py add-phase` (en la fase de implementación, no ahora).

---

```text
PHASE24_DESIGN_REV2=PASS
DELIVERABLES=5
NEW_DEPENDENCIES=NO
SYSTEMD_TIMER_PROPOSED=YES
PAPER_IMPACT=NO
WF_HOLDOUT_IMPACT=NO
FROZEN_SPLITS_UNCHANGED=YES
FUTURE_COLLECTION_DEFINED=YES
RESEARCH_ACCESS_FAIL_CLOSED=YES
DAILY_REFRESH_NOW_USEFUL=YES
READY_FOR_PHASE24_APPROVAL=YES
```

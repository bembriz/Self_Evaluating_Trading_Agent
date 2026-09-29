# ADR-0008 — Automatizacion diaria del refresh Medallion

**Fecha:** 2026-09-29
**Estado:** accepted (Phase 24 bootstrap)

## Contexto

Phase 23 dejo operativo el pipeline Medallion manual para Bronze, Silver trades,
Silver candles, Gold y replay trade-level. Sin automatizacion, el historico queda
obsoleto, los backfills dependen de ejecuciones manuales y no existe una forma
simple de detectar dias faltantes o fallos parciales.

El refresh debe respetar restricciones duras del producto: los splits de evaluacion
congelados en `splits/v1.json` no cambian, `WALK_FORWARD` y `FINAL_HOLDOUT` no se
leen automaticamente para research/replay/tuning, y las fechas posteriores al holdout
solo pueden entrar como `FUTURE_COLLECTION` / `UNASSIGNED` hasta que exista un gate
humano de promocion a Gold/evaluacion. La certificacion paper tampoco debe ser
reiniciada, detenida ni contaminada por el refresh.

Tambien aplican las decisiones previas de Medallion: Bronze es inmutable, Silver es
determinista, Gold es inmutable, `/srv/data` es canonico, `/srv/fast` es cache
reproducible, y las operaciones deben fallar cerrado ante marker/volumen/espacio/hash
invalido.

## Decision

Automatizar Phase 24 con un **systemd timer diario a las 06:20 UTC** que ejecuta un
servicio `Type=oneshot` y un wrapper operativo minimo, delegando la logica principal a
`src/infrastructure/medallion/` sin nuevas dependencias.

La automatizacion aprobada queda definida asi:

- `OnCalendar=*-*-* 06:20:00 UTC`, `Persistent=true`, logs retenidos 30 dias.
- Orquestador Python en `src/infrastructure/medallion/`, usando stdlib y codigo
  Medallion existente; wrapper shell/systemd minimo para operacion.
- Sin Airflow, Kafka, daemon Python permanente, nuevos paquetes, firewall/proxy ni
  infraestructura extra.
- Bronze puede usar HTTPS contra `public.bybit.com`, validado en codigo fuente y sin
  credenciales.
- Transformaciones Silver/Candles/Gold se ejecutan sin red.
- Cache Medallion en `/srv/fast` con cuota inicial `SSD_CACHE_MAX_GB=64`; canonicidad
  permanece en `/srv/data`.
- Gold no tiene borrado automatico.
- `DEVELOPMENT`, `WALK_FORWARD` y `FINAL_HOLDOUT` permanecen exactamente como
  `splits/v1.json`.
- Fechas posteriores a `FINAL_HOLDOUT` se clasifican como `FUTURE_COLLECTION` /
  `UNASSIGNED`: Bronze/Silver pueden recolectarlas, pero Gold/evaluacion/research/replay
  no las leen automaticamente.
- Promocionar `UNASSIGNED` a Gold/evaluacion requiere gate humano explicito y nueva
  politica/versionado de dataset.

## Alternativas consideradas

| Opcion | Consecuencias si se elige |
|---|---|
| systemd oneshot + timer | Menor superficie, auditable, suficiente para refresh diario, reutiliza contenedor/codigo existente |
| Daemon Python permanente | Mas estado operativo, mas fallos de lifecycle y observabilidad sin necesidad real |
| Airflow/Kafka/worker queue | Sobredimensionado para una corrida diaria incremental; introduce dependencias e infraestructura nuevas |
| Cron simple | Menos control de estado, `Persistent=true`, limites y journald que systemd |
| Extender automaticamente los splits | Viola la congelacion de evaluacion y puede contaminar research/replay/tuning |
| Bloquear todo despues del holdout | Preserva splits, pero vuelve inutil el refresh diario cuando ya no hay dias dentro de evaluacion |

## Consecuencias

### Positivas

- El pipeline puede mantenerse actualizado diariamente sin introducir infraestructura
  nueva ni procesos permanentes.
- La separacion `FUTURE_COLLECTION` / `UNASSIGNED` permite continuidad operacional sin
  romper los splits congelados.
- Research, replay, tuning y Gold oficial permanecen fail-closed: solo consumen datasets
  aprobados.
- La operacion es idempotente y reanudable: dias ya completados quedan persistidos y una
  segunda corrida debe converger a no-op.
- La red queda limitada al perfil Bronze y a `public.bybit.com`; las transformaciones se
  mantienen offline.

### Negativas / trade-offs aceptados

- systemd acopla la automatizacion al host lenovosrv; es aceptable porque Phase 24 es una
  automatizacion local del pipeline existente.
- El planner debe mantener una clasificacion explicita por dia, lo que agrega una nueva
  frontera de acceso que debe probarse.
- `UNASSIGNED` acumula datos que no son inmediatamente utilizables para investigacion hasta
  que exista un gate humano de promocion.

### Neutras

- Phase 24 no cambia `splits/v1.json` ni implementa nuevos splits.
- Phase 24 no modifica el Risk Engine, paper trading, LIVE readiness ni certificacion paper.
- La retencion de Gold se documenta, pero no se automatiza borrado en esta fase.

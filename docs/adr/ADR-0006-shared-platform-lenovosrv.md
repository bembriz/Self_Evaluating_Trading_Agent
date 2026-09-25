# ADR-0006 — Plataforma compartida en lenovosrv: infraestructura compartida, aplicaciones aisladas

**Fecha:** 2026-09-24
**Estado:** proposed (gate M0)

## Contexto

lenovosrv hoy ejecuta aplicaciones con infraestructura duplicada o acoplada: GastosIA tiene su propio Caddy y comparte el contenedor PostgreSQL de SETA (`gastos_ia` vive dentro de `self-evaluating-trading-agent-postgres-1`); la app GastosIA está conectada además a la red Docker del proyecto SETA; SETA tiene su propio Prometheus/Grafana/Postgres. Con la iniciativa Medallion (workers, BD de datos, backups) duplicar servicios por aplicación escala mal: más superficie, más imágenes, más backups descoordinados, más coste de mantenimiento. Restricción dura: la certificación paper vigente no puede interrumpirse.

## Decisión

**`SHARE INFRASTRUCTURE · ISOLATE BUSINESS LOGIC`:** lenovosrv evoluciona a una plataforma con servicios compartidos `platform-postgres`, `platform-caddy`, `platform-prometheus`, `platform-grafana` (opcionales futuros `platform-redis`/`platform-backup` solo con necesidad real), y **una base de datos + un rol por solución** sobre un único motor (`trading_agent`→`seta_app`, `gastos_ia`→`gastosia_app`, …) con least privilege, sin credenciales compartidas y backup/restore por BD. Cada solución conserva su **propio contenedor de aplicación** (FastAPI propia: `gastosia-app`, `seta-api`, …) — FastAPI NO se comparte. Red: externa `platform-net` + red privada por solución; `platform-caddy` es el único publicador de 80/443; PostgreSQL jamás expuesto públicamente. Directorios `/srv/docker/{platform,seta,gastosia,future-app}`. M0 solo documenta: **no se crea ni despliega ningún contenedor nuevo** y no se migran BD/redes con certificación activa.

## Alternativas consideradas

| Opción | Consecuencias si se elige |
|---|---|
| Status quo: infraestructura por proyecto | Duplicación creciente (Caddy/PG/monitoring por app), backups y upgrades descoordinados, coste xN con cada solución nueva |
| Compartir todo incluida la app (monolito FastAPI común) | Rompe independencia de dependencias/ciclo de despliegue/fallos/versiones/fronteras de seguridad; un despliegue de una solución afecta a todas |
| Un PostgreSQL por solución (contenedores separados) | Aislamiento fuerte pero coste de RAM/disco/upgrade/backup xN; sin necesidad técnica que lo justifique (multi-tenant por BD+rol ya aísla datos) |
| Migrar ya durante M0 | Riesgo directo sobre la certificación paper activa; viola las restricciones del gate |

## Consecuencias

### Positivas

- Un solo motor/versión de PG, un solo Caddy, un solo stack de monitoring: menos superficie operativa y backups uniformes por BD.
- Aislamiento de datos real por BD+rol: cada solución es un inquilino con credenciales propias.
- Fundación estable para Medallion workers (M8) sin duplicar servicios.

### Negativas / trade-offs aceptados

- Un fallo del motor compartido afecta a todas las soluciones → exige monitoring y backups por BD exigentes (se cubre con platform-prometheus/grafana + backup por BD).
- La migración debe esperar a gates propios (GastosIA y BD de SETA no se mueven en M0–M10 sin aprobación); conviven modelos viejo y nuevo durante el transición.
- Red externa compartida requiere disciplina de conectividad (solo quien necesita `platform-net`).

### Neutras

- GastosIA mantiene su application code en `/srv/docker/gastosia` y sus datos pesados pasan a `/srv/data/gastosia` cuando exista el volumen.
- Si en el futuro una solución exige aislamiento fuerte (GPU, engine separado), la plataforma admite un servicio dedicado excepcional con justificación explícita.

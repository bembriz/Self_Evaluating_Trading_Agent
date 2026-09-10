# Dependency Proposal — DP-005 Local PostgreSQL for Integration Tests

> Obligatoria antes de iniciar un servicio Docker local (PRD §11).
> Flujo: DISCOVER -> PLAN/DRY-RUN -> REPORT -> USER GATE -> APPLY -> VALIDATE -> EVIDENCE.

## Propuesta

| Campo | Valor |
|---|---|
| Nombre | PostgreSQL local para pruebas de integración de Fase 16 |
| Versión propuesta | `pgvector/pgvector:pg16` (ya declarada en `compose.yaml`) |
| Tipo | Imagen Docker y servicio local existente |
| Comando de APPLY | `sudo docker compose up -d postgres` |

## Problema que resuelve

La suite completa falla en 15 pruebas de integración porque no hay PostgreSQL
escuchando en `127.0.0.1:5433`.

## Por qué es necesario

Las pruebas verifican Alembic, repositorios y persistencia de paper trading con
PostgreSQL real. Ejecutar solo unidades no valida esos límites de integración.

## Alternativas consideradas

| Alternativa | Por qué se descarta |
|---|---|
| No iniciar PostgreSQL | Mantiene 15 errores de integración y no permite verificar la suite completa. |
| Mock de PostgreSQL | No prueba migraciones, SQLAlchemy ni pgvector reales. |
| Iniciar `paper-runner`, Grafana o Prometheus | No son necesarios para las pruebas y ampliarían el alcance. |

## Razón para NO implementarlo internamente

PostgreSQL y pgvector son dependencias externas que deben ejecutarse mediante
el servicio Compose versionado; no son sustituibles por código del producto.

## Impacto en arquitectura

Inicia únicamente el servicio `postgres` existente. No cambia código,
esquema, puertos, firewall ni configuración del servidor remoto. El puerto se
limita a loopback y los datos viven en el volumen Docker local `pgdata`.

## Seguridad

La imagen está fijada a `pgvector/pgvector:pg16`. No se usarán ni mostrarán
secretos. La base queda accesible solo desde `127.0.0.1`; no se inicia ningún
servicio de trading ni se contacta Bybit.

## Impacto en licencia del proyecto

No se agregan dependencias al proyecto. La imagen existente se usa solo para
desarrollo y pruebas locales.

## Rollback

Ejecutar `sudo docker compose stop postgres`. El volumen `pgdata` se conserva
para evitar destrucción de datos; su eliminación requerirá autorización
explícita adicional.

## DRY-RUN ejecutado (pre-gate)

```bash
docker compose config --services
docker compose ps --all
docker image inspect pgvector/pgvector:pg16 --format '{{.Id}}'
```

`docker compose config --services` confirmó los servicios declarados. Los dos
comandos de inspección del daemon devolvieron permiso denegado, por lo que el
APPLY y la validación se ejecutarán mediante `sudo` tras aprobación.

---

**DECISIÓN DEL USUARIO:** ☒ APPROVED ☐ REJECTED — Fecha: 2026-09-02. Comentario: "apruebo".

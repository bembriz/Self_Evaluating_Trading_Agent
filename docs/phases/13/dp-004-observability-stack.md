# Dependency Proposal — DP-004: Stack de dashboard y observabilidad (Fase 13)

> Obligatoria ANTES de instalar cualquier paquete, herramienta, imagen o servicio (PRD §11).
> Flujo: DISCOVER → PLAN/DRY-RUN → REPORT (este documento) → USER GATE → APPLY → VALIDATE → EVIDENCE.

## Propuesta

| Campo | Valor |
|---|---|
| Nombre | `jinja2` + `prometheus-client` + `opentelemetry-sdk` + `opentelemetry-instrumentation-fastapi` + HTMX (asset estático) |
| Versión propuesta | últimas estables resueltas por uv (jinja2==3.1.6; otel sdk/instr 0.65b0) |
| Tipo | ☒ paquetes Python + ☒ asset estático vendido (htmx.min.js, sin CDN) + ☒ imágenes Docker en compose (prometheus, grafana — ya existía pgvector/pg16) |
| Comando de instalación | `uv add jinja2 prometheus-client opentelemetry-sdk opentelemetry-instrumentation-fastapi` |

## Problema que resuelve

Fase 13 (PRD §79): vistas Jinja2 del dashboard de trading (PRD §52-53), métricas técnicas PRD §62 expuestas en formato Prometheus, tracing OTel y UI de auditoría. Falta el motor de plantillas, el cliente de métricas y el SDK de tracing.

## Por qué es necesario

Sin Jinja2 no hay vistas server-side; sin `prometheus-client` no hay endpoint `/metrics`; sin OTel no hay trazas de latencias/errores exigidas por PRD §61-62. "No hacer nada" deja los 8 entregables de la fase bloqueados.

## Alternativas consideradas

| Alternativa | Por qué se descarta |
|---|---|
| Plantillas con f-strings / HTML manual | Escapado y mantenimiento imposibles a medio plazo; Jinja2 es el estándar de FastAPI |
| `prometheus-fastapi-instrumentator` | Añade dependencia extra sobre prometheus-client; exponer métricas manualmente da control fino de §62 |
| htmx vía CDN | Dependencia externa en runtime; se VENDE el archivo estático (~14KB) |
| Grafana/OTel collector como SaaS | PRD §61 exige stack local OpenTelemetry+Prometheus+Grafana; datos nunca salen del entorno |

## Razón para NO implementarlo internamente

Formato de exposición de métricas de Prometheus y propagación de contexto W3C de OTel son protocolos estandarizados; reimplementarlos garantiza incompatibilidad con los dashboards/collectors estándar.

## Impacto en arquitectura

- Jinja2: solo capa `interfaces/web` (plantillas).
- prometheus-client: registro global en `infrastructure/observability` + endpoint `/metrics`.
- OTel: instrumentación FastAPI opcional por config (`otel_enabled=false` por defecto); sin colector obligatorio para correr tests.
- compose.yaml: servicios `prometheus` y `grafana` (solo levantables con Docker; validación de esta parte pendiente de entorno).
- HTMX: polling simple sobre endpoints existentes; sin framework frontend.

## Seguridad

- jinja2 3.1.6: BSD-3-Clause, mantenido por Pallets. Autoescape activado por defecto en FastAPITemplates.
- prometheus-client 0.26.0: Apache-2.0.
- opentelemetry-sdk/api/instrumentation 0.65b0: Apache-2.0, CNCF.
- htmx 2.x: BSD-2-Clause, archivo vendido con hash verificado.
- Imágenes Docker oficiales: `prom/prometheus`, `grafana/grafana`. Grafana sin credenciales por defecto expuestas al host salvo localhost.

## Impacto en licencia del proyecto

Todas permisivas (BSD/Apache); sin cambios de licenciamiento.

## Rollback

`uv remove <paquetes>`; revertir compose.yaml; borrar carpeta templates/static. Endpoint `/metrics` tras feature flag.

## DRY-RUN ejecutado (pre-gate)

```bash
$ uv pip install --dry-run jinja2
 + jinja2==3.1.6                       # 1-2 paquetes

$ uv pip install --dry-run jinja2 prometheus-client opentelemetry-sdk opentelemetry-instrumentation-fastapi
 # ~11 paquetes ligeros (sin binarios pesados): otel api/sdk/util-http, wrapt, prometheus-client...
```

Nota de entorno: Docker sigue ausente; Prometheus/Grafana en compose quedarán configurados pero su validación queda pendiente de entorno (como integration tests).

---

**DECISIÓN DEL USUARIO:** ☒ APPROVED ☐ REJECTED — Fecha: 2026-08-24 Comentario: Aprobado en sesión.

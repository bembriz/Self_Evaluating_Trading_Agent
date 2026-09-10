# Prometheus Production Preflight — Fase 16c.3

> **Estado:** PREFLIGHT — esperando GATE. No desplegar en lenovosrv todavía.

## Objetivo

Levantar Prometheus (retention ≥45d, volumen persistente, red interna Docker, sin exposición pública) para scrapear `/metrics` del paper-runner, **sin** afectar al runner.

## Comandos exactos

```bash
# 1. Validación previa (read-only, sin cambios)
docker compose config                # valida sintaxis de compose.yaml

# 2. APPLY (solo tras GATE APPROVED)
docker compose up -d prometheus

# 3. Verificar targets (paper-runner:9090 debe estar "up")
curl -s http://127.0.0.1:9090/api/v1/targets | python3 -m json.tool

# 4. Verificar retención activa
docker exec <prometheus-container> promtool check config /etc/prometheus/prometheus.yml
```

## Compose diff

```diff
   prometheus:
     image: prom/prometheus:v2.53.0
+    command:
+      - --config.file=/etc/prometheus/prometheus.yml
+      - --storage.tsdb.retention.time=${PROMETHEUS_RETENTION:-45d}
     volumes:
       - ./deploy/prometheus.yml:/etc/prometheus/prometheus.yml:ro
       - promdata:/prometheus
     ports:
       - "127.0.0.1:9090:9090"
```

## Puertos

| Servicio | Puerto interno | Publicado en host | Exposición |
|---|---|---|---|
| paper-runner `/metrics` | `0.0.0.0:9090` (en el contenedor) | **NO publicado** | solo red Docker interna |
| prometheus | `9090` (contenedor) | `127.0.0.1:9090` (loopback) | solo loopback |

> El `/metrics` del paper-runner **no se publica al host** (`compose.yaml` no define `ports` en paper-runner). Prometheus lo scrapea por la red interna Docker (`paper-runner:9090`).

## Network

Red por defecto de Docker Compose (misma red para todos los servicios del `compose.yaml`). Prometheus alcanza `paper-runner:9090` por nombre de servicio. Sin red externa ni exposición pública.

## Volume

`promdata` (named volume) montado en `/prometheus` (TSDB). Persiste entre reinicios del contenedor de Prometheus.

## Retention

`--storage.tsdb.retention.time=${PROMETHEUS_RETENTION:-45d}` → **45 días** por defecto (configurable vía env `PROMETHEUS_RETENTION`).

## Estimación de storage

- 1 target, ~15 métricas, `scrape_interval: 5s`, 45 días.
- Scrapes: `45 × 86400 / 5 ≈ 777,600`; muestras ≈ `777,600 × 15 ≈ 11.7M`.
- TSDB (comprimido): ~1–2 bytes/muestra → **~15–25 MB**.
- Cota conservadora: **< 1 GB**. Sin impacto material.

## Health checks

- Prometheus v2.53 expone su propio `/metrics` y `/api/v1/targets`. Healthcheck opcional:
  ```yaml
  healthcheck:
    test: ["CMD-SHELL", "wget -qO- http://localhost:9090/-/healthy || exit 1"]
    interval: 30s
    timeout: 5s
    retries: 3
  ```
- No se añade por defecto (Prometheus no tiene endpoint `/-/healthy` en todas las versiones); se verifica con `/api/v1/targets`.

## Rollback

```bash
docker compose stop prometheus      # detiene; volumen promdata se conserva
# revertir: eliminar el bloque "command" añadido en compose.yaml
```

## Impacto sobre paper-runner

**Ninguno.** El paper-runner **no** depende de Prometheus (`compose.yaml` paper-runner no tiene `depends_on: prometheus`). Si Prometheus cae o no existe, el runner sigue operando; su servidor `/metrics` (thread daemon) simplemente no recibe scrapes.

## Métricas a scrapear (ya existentes)

`seta_ws_status`, `seta_reconnects_total`, `seta_errors_total{kind="ws"}`, `seta_ws_stale_total`, `seta_candles_processed_total`, `seta_atr_ready`, `seta_llm_cost_usd`.

---

**DECISIÓN:** ☐ GATE APPROVED → autorizar despliegue productivo de Prometheus ☐ REJECTED

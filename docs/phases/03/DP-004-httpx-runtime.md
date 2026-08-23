# Dependency Proposal — DP-004: httpx como dependencia runtime (adapter Bybit)

> Obligatoria ANTES de instalar cualquier paquete, herramienta, imagen o servicio (PRD §11).
> Flujo: DISCOVER → PLAN/DRY-RUN → REPORT (este documento) → USER GATE → APPLY → VALIDATE → EVIDENCE.

## Propuesta

| Campo | Valor |
|---|---|
| Nombre | `httpx` |
| Versión propuesta | `httpx>=0.28.1` (ya presente en el lockfile como dev dependency) |
| Tipo | ☑ paquete Python (runtime) ☐ paquete Python (dev) ☐ CLI ☐ imagen Docker ☐ servicio ☐ extensión/MCP |
| Comando de instalación | `uv add httpx` (pasa de `[dependency-groups].dev` a `[project].dependencies`) |

## Problema que resuelve

Fase 03 exige un adapter REST histórico de Bybit (`src/infrastructure/bybit/client.py`) que consume `GET /v5/market/kline`. Ese código vive en producción (`src/infrastructure/`) y por tanto su cliente HTTP debe ser una dependencia de runtime, no de dev. Hoy `httpx` está declarado únicamente en el grupo `dev` (lo añadió DP-003 para el `TestClient` de FastAPI).

## Por qué es necesario

- El adapter Bybit (Fase 03, 04, 12) hace llamadas HTTP async reales en runtime.
- El PRD §10 fija el stack sobre FastAPI/pydantic; `httpx` es el cliente HTTP async estándar del ecosistema y ya es la base de `fastapi.testclient` (por eso está en el lockfile).
- La alternativa "no hacer nada" deja el adapter importando `httpx` desde una dependencia dev → en producción (`uv sync --no-dev` o el contenedor) `import httpx` fallaría.

## Alternativas consideradas

| Alternativa | Por qué se descarta |
|---|---|
| `aiohttp` | Nueva dependencia con más superficie; duplicaría la funcionalidad de `httpx`, que ya está instalado y es la elección estándar en este stack. |
| `urllib`/stdlib (`urllib.request`) | Solo sincrónico; la app y los repos son async por defecto (PRD §54, fastapi-standards). Bloquearía el event loop. |
| Implementación propia | Reimplementar un cliente HTTP con timeouts, retries, backoff y `Retry-After` es inviable y arriesgado. |

## Razón para NO implementarlo internamente

`httpx` es el cliente HTTP async/ sync maduro, con `MockTransport` para tests offline y soporte de timeouts/retries; ya está auditado en el lockfile. No hay motivo para escribir un cliente propio.

## Impacto en arquitectura

Ninguno estructural: se mueve `httpx` de `[dependency-groups].dev` a `[project].dependencies` en `pyproject.toml` (y se regenera `uv.lock`). El nuevo módulo `src/infrastructure/bybit/` pasa a depender de una runtime dep correcta. Sin cambios en `domain/`, `application/` ni en otros adapters.

## Seguridad

- Licencia BSD-3 (httpx), compatible con el proyecto.
- Ya auditado vía `pip-audit` en el lockfile de DP-003 (no introduce una dependencia nueva, solo reclasifica una existente).
- El endpoint kline spot de Bybit es público: no se requiere API key, por lo que no hay secretos nuevos.

## Impacto en licencia del proyecto

Sin cambios (BSD-3 ya presente).

## Rollback

- `uv add --dev httpx` para devolverla al grupo dev (o revertir el diff de `pyproject.toml` + `uv lock`).
- Sin efecto persistente más allá de la clasificación de la dependencia.

## DRY-RUN ejecutado (pre-gate)

```bash
# DISCOVER (solo lectura) ya ejecutado 2026-08-23:
uv pip list | grep -i httpx   # httpx 0.28.1 (instalado, en grupo dev)
grep -n "httpx" pyproject.toml  # httpx>=0.28.1 en [dependency-groups].dev
curl -s "https://api.bybit.com/v5/market/kline?category=spot&symbol=ETHUSDT&interval=15&limit=2"  # 200 OK, endpoint público funciona
```

---

**DECISIÓN DEL USUARIO:** ☑ APPROVED ☐ REJECTED — Fecha: 2026-08-23 Firma/comentario: aprobado vía selector OpenCode (gate DP-004)

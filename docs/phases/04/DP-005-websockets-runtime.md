# Dependency Proposal — DP-005: websockets como dependencia runtime (cliente WS Bybit)

> Obligatoria ANTES de instalar cualquier paquete, herramienta, imagen o servicio (PRD §11).
> Flujo: DISCOVER → PLAN/DRY-RUN → REPORT (este documento) → USER GATE → APPLY → VALIDATE → EVIDENCE.

## Propuesta

| Campo | Valor |
|---|---|
| Nombre | `websockets` |
| Versión propuesta | `websockets>=17.0` (ya presente en `uv.lock` como transitiva de `uvicorn[standard]`) |
| Tipo | ☑ paquete Python (runtime) ☐ paquete Python (dev) ☐ CLI ☐ imagen Docker ☐ servicio ☐ extensión/MCP |
| Comando de instalación | `uv add websockets` (pasa de transitiva a dependencia directa runtime) |

## Problema que resuelve

Fase 04 exige un cliente WebSocket de Bybit producción (`src/infrastructure/bybit/ws.py`) para order book + candles en vivo. `httpx` (Fase 03) es solo HTTP; no soporta WebSocket. El adapter WS importará `websockets` directamente, por lo que debe ser dependencia runtime directa (no confiar en que `uvicorn[standard]` la traiga como transitiva).

## Por qué es necesario

- El PRD §14 exige mantener un order book local vía WebSocket con snapshot+deltas y reconexión.
- `websockets` es el cliente WebSocket async estándar de Python, ya instalado en el lockfile (transitivo de `uvicorn[standard]`), por lo que no añade superficie nueva de suministro: solo reclasifica una dependencia existente.
- La alternativa "no hacer nada" deja el adapter WS importando una dependencia transitiva (frágil si `uvicorn[standard]` cambia su extra).

## Alternativas consideradas

| Alternativa | Por qué se descarta |
|---|---|
| `aiohttp` | Cliente HTTP+WS más pesado; duplicaría HTTP (ya cubierto por httpx) y añadiría una dependencia nueva con más superficie. |
| `websocket-client` (sync) | Sincrónico; bloquea el event loop. La app y los workers son async (PRD §54/§63). |
| Implementación propia del protocolo WS | Reimplementar framing WS, ping/pong y reconexión es inviable y arriesgado. |

## Razón para NO implementarlo internamente

`websockets` es maduro, mantenido por el proyecto Python (PSF-adjacent), con soporte de reconexión, ping/pong y async nativo. Ya está auditado en `uv.lock`.

## Impacto en arquitectura

Ninguno estructural: `websockets` pasa de dependencia transitiva a directa en `[project].dependencies` (y se regenera `uv.lock`). El nuevo módulo `src/infrastructure/bybit/ws.py` la importa. Sin cambios en `domain/`, `application/` ni en los adaptadores HTTP existentes.

## Seguridad

- Licencia BSD-3 (websockets), compatible con el proyecto.
- Ya auditado vía `pip-audit` en el lockfile (no introduce dependencia nueva; reclasifica una existente).
- El WebSocket público de Bybit (`wss://stream.bybit.com/v5/public/spot`) no requiere API key (solo market data público).

## Impacto en licencia del proyecto

Sin cambios (BSD-3 ya presente).

## Rollback

- `uv remove websockets` (o revertir el diff de `pyproject.toml` + `uv lock`); vuelve a ser transitiva de `uvicorn[standard]`.

## DRY-RUN ejecutado (pre-gate)

```bash
# DISCOVER (solo lectura) ya ejecutado 2026-08-23:
uv pip list | grep -i websockets      # websockets 17.0.1 (transitiva de uvicorn[standard])
grep -n "websockets" pyproject.toml   # NO está en [project].dependencies (solo en uv.lock)
uv run python -c "import websockets; print(websockets.__version__)"  # 17.0.1
# Captura real de wss://stream.bybit.com/v5/public/spot: snapshot/delta/kline OK (sin API key)
```

---

**DECISIÓN DEL USUARIO:** ☑ APPROVED ☐ REJECTED — Fecha: 2026-08-23 Firma/comentario: aprobado vía selector OpenCode (gate DP-005)

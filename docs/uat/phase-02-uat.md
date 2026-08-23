# UAT — Fase 02: PostgreSQL & Application Skeleton

> Prueba de aceptación de usuario (HITL). El agente NO puede aprobar UAT.
> Ejecuta los pasos tal cual y completa "Resultado observado" y el veredicto final.

## Precondiciones

| # | Precondición | Verificada ☐ |
|---|---|---|
| 1 | Docker instalado y con permisos (o `sudo docker`) | ☐ |
| 2 | `uv` instalado y `uv sync` ya ejecutado | ☐ |
| 3 | Crear `.env` con `POSTGRES_PASSWORD=trading` (y resto de POSTGRES_* si aplica) | ☐ |
| 4 | Terminal en la raíz del repositorio | ☐ |

## Entradas / Datos

`.env` con `POSTGRES_PASSWORD` (no versionado). Nada más.

## Pasos

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | `sudo docker compose up -d postgres` | Contenedor `pgvector/pgvector:pg16` healthy en 127.0.0.1:5433 |
| 2 | `uv run alembic upgrade head` | Migración `0001` aplicada, exit 0 |
| 3 | `uv run alembic downgrade base && uv run alembic upgrade head` | Roundtrip sin errores |
| 4 | `uv run pytest --cov=src --cov-branch --cov-fail-under=90` | `18 passed` y cobertura 100% |
| 5 | `uv run ruff check . && uv run ruff format --check .` | Sin errores |
| 6 | `uv run mypy src tests` | "Success: no issues found" |
| 7 | `uv run uvicorn interfaces.api.app:app --port 8000` y en otra terminal: `curl localhost:8000/health`, `curl localhost:8000/ready`, `curl localhost:8000/api/v1/system/state` | 200 en los tres; `/ready` → `{"status":"ready"}`; `/state` → `trading_mode backtest, live false` |
| 8 | `sudo docker build -t self-evaluating-trading-agent:dev .` | Imagen construida exit 0 |

## Evidencia a adjuntar

Salida de cada comando (pasos 1–8).

## Resultado observado

| Paso | Resultado observado | ¿Coincide? (SÍ/NO) | Notas |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |
| 6 | | | |
| 7 | | | |
| 8 | | | |

## Incidencias encontradas

> Desviaciones, errores o comportamientos inesperados.

---

## VEREDICTO UAT: APPROVED
<!-- Sustituir PENDING por APPROVED o REJECTED. gate_check exige el veredicto APPROVED visible (los comentarios HTML no cuentan) al check uat-approved -->
Decisor: usuario  Fecha: 2026-08-23
Comentario: aprobado vía selector OpenCode

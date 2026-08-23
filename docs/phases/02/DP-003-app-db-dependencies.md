# Dependency Proposal — DP-003: App skeleton (FastAPI/SQLAlchemy/Alembic) + postgres/pgvector

> Obligatoria ANTES de instalar cualquier paquete, herramienta, imagen o servicio (PRD §11).
> Flujo: DISCOVER → PLAN/DRY-RUN → REPORT (este documento) → USER GATE → APPLY → VALIDATE → EVIDENCE.

## Propuesta

| Campo | Valor |
|---|---|
| Nombre | `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `alembic`, `psycopg[binary]`, `pydantic-settings`, `pyyaml` + dev `httpx`, `pytest-asyncio` + imagen `pgvector/pgvector:pg16` |
| Versión propuesta | `fastapi>=0.115`, `uvicorn[standard]>=0.30`, `sqlalchemy[asyncio]>=2.0`, `alembic>=1.13`, `psycopg[binary]>=3.2`, `pydantic-settings>=2.5`, `pyyaml>=6.0`; dev `httpx>=0.27`, `pytest-asyncio>=0.24` |
| Tipo | ☑ paquete Python (runtime) ☑ paquete Python (dev) ☑ imagen Docker ☐ CLI ☐ servicio |
| Comando de instalación | `uv add ...` (runtime+dev); `docker compose up -d postgres` (pull `pgvector/pgvector:pg16`) |

## Problema que resuelve

Fase 02 exige: FastAPI base con `/health`/`/ready`, SQLAlchemy 2.x, Alembic con migraciones, PostgreSQL + pgvector, configuración por entorno (YAML + .env) y patrón puerto/adaptador de persistencia (PRD §54–58). Sin estas dependencias la fase no es implementable ni verificable.

## Por qué es necesario

Son el stack que fija el PRD §10 (FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, PostgreSQL, pgvector) y las skills `fastapi-standards`, `postgres-pgvector-alembic`, `configuration-environments`. La alternativa "no hacer nada" bloquea todo el desarrollo de producto posterior (market data, decisiones, memoria, ejecución dependen de esta base).

## Alternativas consideradas

| Alternativa | Por qué se descarta |
|---|---|
| `asyncpg` como driver async | `psycopg[binary]` sirve para sync (Alembic) **y** async (app) con un único driver, y tiene soporte pgvector. Un solo driver = menos complejidad. |
| `psycopg2-binary` (sync-only) | No soporta async; la app es async por defecto (PRD §54 / fastapi-standards). |
| `pydantic-settings` + `python-dotenv` frente a loader custom | El PRD §58 pide `config/*.yaml`; pydantic-settings v2 integra YAML + `.env` con precedencia correcta (env > yaml) sin escribir un loader propio. |
| Postgres vanilla (sin pgvector) | La Trading Memory (Fase 09) y el modelo PRD §55 requieren `vector`; la imagen `pgvector/pgvector` trae la extensión lista. |
| `pgvector` (paquete Python) ahora | No se crea ninguna columna `vector` en Fase 02 (solo `CREATE EXTENSION`); el paquete se añade en Fase 09 (YAGNI). |

## Razón para NO implementarlo internamente

Reimplementar un servidor web async, un ORM, un sistema de migraciones o un motor de configuración tipada es inviable y arriesgado; son herramientas maduras de ecosistema con alta adopción.

## Impacto en arquitectura

Añade el plano de persistencia e interfaz: `src/infrastructure/database/` (SQLAlchemy+Alembic), `src/interfaces/api/` (FastAPI), `src/application/ports` + `services`, `src/settings.py`, `migrations/`, `config/*.yaml`, `compose.yaml`. El dominio sigue sin tocar. `uv.lock` y `pyproject.toml` pasan a tener runtime deps (antes `[]`).

## Seguridad

- Todas licencias MIT/BSD/PSF/Apache-2.0 compatibles (FastAPI MIT, SQLAlchemy MIT, psycopg LGPL-3, pydantic MIT, Alembic MIT, uvicorn BSD-3). psycopg es LGPL (uso como librería, sin modificación → compatible).
- `psycopg[binary]` descarga un wheel binario; se fija versión en `uv.lock`.
- La contraseña de Postgres vive SOLO en `.env` (gitignored); `.env.example` sin credenciales. Imagen oficial `pgvector/pgvector` (no `latest`, tag `pg16`).
- Puerto Postgres publicado solo a `localhost` en `compose.yaml` (no `0.0.0.0`).

## Impacto en licencia del proyecto

Sin cambios: dependencias MIT/BSD/Apache-2.0 + psycopg LGPL-3 (uso como librería). No afectan la licencia del producto.

## Rollback

- `uv remove fastapi uvicorn sqlalchemy alembic psycopg pydantic-settings pyyaml httpx pytest-asyncio` + borrar `.venv/` + `uv sync`.
- `docker compose down -v` (borra volumen) y borrar `compose.yaml`; la imagen se elimina con `docker rmi pgvector/pgvector:pg16`.
- Borrar `src/infrastructure/database/`, `src/interfaces/api/`, `migrations/`, `config/`, `alembic.ini`.

## DRY-RUN ejecutado (pre-gate)

```bash
# DISCOVER (solo lectura) ya ejecutado 2026-08-23:
uv --version          # 0.11.25 · Python 3.12.13 (pinned)
docker --version      # 29.7.2
# No hay ninguno de estos paquetes instalados aún en el producto (runtime deps = [])
# Imagen pgvector/pgvector:pg16 aún no descargada
```

---

**DECISIÓN DEL USUARIO:** ☑ APPROVED ☐ REJECTED — Fecha: 2026-08-23 Firma/comentario: aprobado vía selector OpenCode (gate DP-003)

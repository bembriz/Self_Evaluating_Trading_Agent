# Phase 02 — PostgreSQL & Application Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development o superpowers:executing-plans. Steps usan checkbox (`- [ ]`).

**Goal:** Montar el esqueleto de aplicación FastAPI + persistencia PostgreSQL/pgvector con Alembic, configuración por entorno (YAML + .env) y el patrón puerto/adaptador de persistencia, listo para las fases de datos.

**Architecture:** Monolito hexagonal (PRD §8–9). `interfaces/api` (FastAPI delgada), `application/services` (orquestación) + `application/ports` (Protocols), `infrastructure/database` (SQLAlchemy 2.x + Alembic, adaptadores de repositorios). Config en `config/*.yaml` + `.env` (pydantic-settings). `src` sigue siendo src-layout (módulos top-level `main.py`, `version.py`, `settings.py`).

**Tech Stack:** FastAPI, Uvicorn, SQLAlchemy 2.x (async, psycopg3), Alembic, Pydantic v2 + pydantic-settings, PostgreSQL 16 + pgvector (imagen `pgvector/pgvector:pg16`), Docker Compose.

## Global Constraints

- Sin instalación sin DP-003 APPROVED (PRD §11): `uv add`, `docker compose up`, `docker pull`.
- Estructura hexagonal: `domain ← application ← interfaces`; `infrastructure` implementa puertos (arquitectura-hexagonal).
- Async por defecto para I/O (FastAPI + SQLAlchemy async); endpoint delgado, lógica en `application/services`.
- Alembic obligatorio para TODO cambio de esquema; toda migración con `upgrade()` + `downgrade()` + test up→down→up (PRD §56).
- Secrets SOLO en `.env` (nunca versionado); `.env.example` sin credenciales (PRD §58–59, security-secrets).
- Coverage `--cov=src --cov-branch --cov-fail-under=90`; mypy strict.
- No crear las 20+ entidades de PRD §55 ahora: solo esquema inicial mínimo (`system_state` + extensión `vector`). Las demás llegan con su fase.
- Grafo de codebase-memory a la par (AGENTS.md §4.13): re-index tras commit.

---

### Task 1: DP-003 + USER GATE

**Files:** Create `docs/phases/02/DP-003-app-db-dependencies.md`

**Produces:** decisión APPROVED que desbloquea `uv add`, `docker compose up`, `docker pull`.

- [ ] **Step 1:** Escribir la proposal (runtime fastapi/uvicorn/sqlalchemy[asyncio]/alembic/psycopg[binary]/pydantic-settings/pyyaml; dev httpx/pytest-asyncio; imagen `pgvector/pgvector:pg16`).
- [ ] **Step 2:** Presentar al usuario y esperar APPROVED.

---

### Task 2: Dependencias + config base

**Files:** Modify `pyproject.toml`; Create `config/base.yaml`, `config/backtest.yaml`, `config/replay.yaml`, `config/paper.yaml`, `config/live.yaml`; Modify `.env.example`

**Consumes:** DP-003 APPROVED.

- [ ] **Step 1:** `uv add fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" alembic "psycopg[binary]" pydantic-settings pyyaml`
- [ ] **Step 2:** `uv add --dev httpx pytest-asyncio`
- [ ] **Step 3:** Crear `config/base.yaml` (defaults seguros: postgres host/port/db/user, app_name, trading_mode=backtest, live disabled).
- [ ] **Step 4:** Crear los 4 stubs de modo (`backtest/replay/paper/live.yaml`) con comentario de que se cablean en fases posteriores.
- [ ] **Step 5:** Extender `.env.example` con `POSTGRES_HOST/PORT/DB/USER/PASSWORD` (vacíos, sin credenciales reales).
- [ ] **Step 6:** `uv lock` y commit (con autorización).

---

### Task 3: Settings (pydantic-settings) — TDD

**Files:** Create `src/settings.py`; Test `tests/test_settings.py`

**Interfaces:**
- Produce `Settings` (BaseSettings) con `app_name`, `app_version`, `trading_mode`, `live_trading_enabled`, `postgres.host/port/db/user/password` y propiedad `database_url -> str`. Factory `load_settings()` lee `config/base.yaml` + `.env` (env gana).

- [ ] **Step 1:** Test que falla: `test_load_settings_defaults`, `test_database_url_compone_sin_password`, `test_env_override` (monkeypatch `POSTGRES_PORT`).
- [ ] **Step 2:** Implementar `src/settings.py`.
- [ ] **Step 3:** Test verde + `mypy src` + `ruff`.

---

### Task 4: SQLAlchemy base + modelo inicial

**Files:** Create `src/infrastructure/database/base.py`, `src/infrastructure/database/session.py`, `src/infrastructure/database/models.py`

**Interfaces:**
- Produce `Base` (DeclarativeBase), `create_engine(settings) -> AsyncEngine`, `async_session_factory`, y modelo `SystemState` (`id`, `key` único, `value` JSON, `updated_at` UTC).

- [ ] **Step 1:** Test de modelo (mapeo): instancia `SystemState(key="trading_mode", value={"mode": "backtest"})` con `value` como JSON dict.
- [ ] **Step 2:** Implementar los 3 módulos.
- [ ] **Step 3:** Test verde + mypy/ruff.

---

### Task 5: Alembic inicial (extensión vector + system_state)

**Files:** Create `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/0001_initial.py`

**Interfaces:**
- Produce migración `0001_initial`: `CREATE EXTENSION IF NOT EXISTS vector` + tabla `system_state`. `env.py` usa settings para el `sqlalchemy.url`.

- [ ] **Step 1:** Generar scaffold Alembic y escribir `0001_initial` con `upgrade()`/`downgrade()` (downgrade: `DROP TABLE system_state` + `DROP EXTENSION vector`).
- [ ] **Step 2:** Test integration up→down→up contra DB efímera (Task 7/8).
- [ ] **Step 3:** Evidencia.

---

### Task 6: Puerto de persistencia + adaptador SQLAlchemy

**Files:** Create `src/application/ports/repositories.py`; `src/infrastructure/database/repositories.py`

**Interfaces:**
- Produce Protocol `SystemStateRepository` con `get(key) -> dict | None` y `set(key, value) -> None`; adaptador `SqlAlchemySystemStateRepository(session)`.

- [ ] **Step 1:** Unit test del adaptador con DB real (integration) + test del protocolo.
- [ ] **Step 2:** Implementar.
- [ ] **Step 3:** Verde + mypy/ruff.

---

### Task 7: FastAPI app + endpoints /health /ready /api/v1/system/state

**Files:** Create `src/interfaces/api/app.py`, `src/interfaces/api/deps.py`, `src/interfaces/api/routers/health.py`, `src/interfaces/api/routers/system.py`; `src/application/services/health.py`

**Interfaces:**
- Produce `create_app(settings) -> FastAPI` (lifespan crea engine/session, inyecta repositorio). GET `/health` (liveness, `{"status":"ok"}`), GET `/ready` (chequea `SELECT 1`, 200/503), GET `/api/v1/system/state` (lee `system_state` de DB).

- [ ] **Step 1:** Tests integration: `/health` 200; `/ready` 200 con DB up; `/api/v1/system/state` devuelve estado sembrado; `/ready` 503 con DB caída (mock).
- [ ] **Step 2:** Implementar app + routers + health service.
- [ ] **Step 3:** Verde + mypy/ruff.

---

### Task 8: Docker Compose postgres+pgvector

**Files:** Create `compose.yaml`; Modify `Dockerfile` (multi-stage uv con runtime deps + CMD uvicorn); Modify `.dockerignore`

- [ ] **Step 1:** `compose.yaml` con servicio `postgres` (`pgvector/pgvector:pg16`, healthcheck `pg_isready`, volumen, env de POSTGRES_*).
- [ ] **Step 2:** `docker compose config` (dry-run, sin up) como validación pre-gate.
- [ ] **Step 3:** Tras APPROVED DP-003: `docker compose up -d postgres` + `pg_isready`.
- [ ] **Step 4:** Dockerfile multi-stage (instala deps con `uv sync --frozen`, `CMD uvicorn interfaces.api.app:app`).
- [ ] **Step 5:** Evidencia.

---

### Task 9: Integration tests contra DB real + cobertura

**Files:** Create `tests/conftest.py` (fixtures: settings de test, engine efímero, alembic up/down), `tests/integration/test_health.py`, `tests/integration/test_repository.py`, `tests/integration/test_alembic.py`

- [ ] **Step 1:** `pytest-asyncio` (`asyncio_mode=auto`) en pyproject.
- [ ] **Step 2:** Fixtures que crean/esquema migran una DB de test (postgres del compose) y la limpian.
- [ ] **Step 3:** Tests: alembic up→down→up; repositorio set/get; /health /ready /api/v1/system/state.
- [ ] **Step 4:** `uv run pytest --cov=src --cov-branch --cov-fail-under=90` con DB up → coverage ≥90%.

---

### Task 10: CI (migrations + integration con servicio postgres)

**Files:** Modify `.github/workflows/ci.yml`

- [ ] **Step 1:** Añadir job `integration`: servicio `pgvector/pgvector:pg16` (healthcheck), `uv sync --frozen`, `alembic upgrade head && alembic downgrade base && alembic upgrade head`, `pytest --cov=src --cov-branch --cov-fail-under=90`.
- [ ] **Step 2:** Validar YAML localmente (`check-yaml`).

---

### Task 11: E2E + evidencia + gate

- [ ] **Step 1:** E2E: `docker compose up -d postgres` → `alembic upgrade head` → arrancar uvicorn → `GET /health`/`/ready`/`/api/v1/system/state` → down.
- [ ] **Step 2:** `mark-done` ×8, `gate_check --phase 02`, reporte (30 secciones), UAT.
- [ ] **Step 3:** Presentar UAT + gate al usuario.

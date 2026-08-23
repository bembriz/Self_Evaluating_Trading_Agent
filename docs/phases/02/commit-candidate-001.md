# Commit Candidate Report — 2026-08-23

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

Cerrar la Fase 02 (PostgreSQL & Application Skeleton): aplicación FastAPI + persistencia PostgreSQL/pgvector con Alembic, configuración por entorno y patrón puerto/adaptador, con gate de fase APPROVED.

## Rama

| Campo | Valor |
|---|---|
| branch | main |
| base commit | 0fd22f3 chore(harness): exigir grafo de codebase-memory en sincronía con commits |

## Archivos

- **Creados (42):** `compose.yaml`, `alembic.ini`, `migrations/**` (env.py, script.py.mako, versions/0001_initial.py), `config/*.yaml` (5), `src/settings.py`, `src/infrastructure/database/{base,session,models,repositories}.py`, `src/application/ports/repositories.py`, `src/interfaces/api/{app,deps}.py`, `src/interfaces/api/routers/{__init__,health,system}.py`, `tests/{conftest,test_settings,test_models,test_handlers}.py`, `tests/integration/{test_alembic,test_repository,test_api}.py`, `docs/phases/02/**`, `docs/phases/phase-02-report.md`, `docs/uat/phase-02-uat.md`, plan de fase.
- **Modificados (10):** `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`, `Dockerfile`, `README.md`, `opencode.json`, `harness/state/progress.yaml`.
- **Eliminados:** ninguno.

## Diff

```
52 files changed, 2172 insertions(+), 43 deletions(-)
```

## Arquitectura afectada

Nuevo plano de persistencia e interfaz (hexagonal): `infrastructure/database` (SQLAlchemy+Alembic), `interfaces/api` (FastAPI), `application/ports` (Protocol `SystemStateRepository`), `settings`. Los handlers dependen del Protocol, no del adaptador. `harness/` intacto salvo el ledger.

## Índice del grafo

- [x] Blast radius con `detect_changes`: 107 símbolos nuevos, 0 impactados.
- [ ] Índice re-indexado tras el commit (`index_repository`)
- [ ] Cobertura verificada sobre archivos tocados (`check_index_coverage`)

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Unit + Integration (`pytest --cov=src --cov-branch --cov-fail-under=90`) | 18/18 PASS | docs/phases/02/evidence/unit-tests.log |
| Alembic roundtrip up→down→up | PASS | docs/phases/02/evidence/alembic-roundtrip.log |
| E2E (uvicorn + curl /health /ready /state) | PASS (3×200) | docs/phases/02/evidence/e2e.log |

## Cobertura

**100.00%** (branch) — gate ≥90%.

## Calidad

```bash
uv run ruff check .              # All checks passed
uv run ruff format --check .     # 46 files already formatted
uv run mypy src tests            # Success: no issues found
uv run pip-audit                 # 0 vulnerabilidades
```

## Seguridad

- [x] Sin secretos en el diff (solo `POSTGRES_PASSWORD=trading` como default dev en compose, nunca en versionado con valor real).
- [x] Sin archivos .env (`.env` gitignored); `.env.example` sin credenciales.
- [x] `opencode.json` mantiene `deny` de `.env` reales; añade `allow` puntual a `.env.example`.

## Riesgos

Bajo. Código nuevo autocontenido. `opencode.json` cambia permisos read/edit SOLO para `.env.example` (requiere reiniciar opencode). Puerto 5433 (evita colisión con postgres ajenos).

## Deuda técnica

Documentada en reporte §24: `.env.example` pendiente tras reinicio; Dockerfile con `pip install uv` in-build; deprecación `httpx`→`httpx2` en TestClient; roundtrip de Alembic duplicado (CI + conftest).

## Mensaje de commit propuesto

```
feat(phase-02): PostgreSQL & Application Skeleton

- FastAPI (create_app + lifespan) con /health /ready /api/v1/system/state
- SQLAlchemy 2.x async (psycopg3) + puerto/adaptador SystemStateRepository
- Alembic async + migración 0001 (extensión vector + system_state)
- config/*.yaml + pydantic-settings (.env para secretos)
- compose.yaml (pgvector/pgvector:pg16) + Dockerfile multi-stage
- CI con job integration (servicio postgres) + tests 100% cobertura
- opencode.json: permitir .env.example (mantiene deny de .env reales)
- DP-003 APPROVED; gate Fase 02 approved
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

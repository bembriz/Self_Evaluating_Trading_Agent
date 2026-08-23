# Reporte de Fase 01 — Python Project Foundation

**Fecha:** 2026-08-23
**Estado de fase:** done
**Avance fase:** 100.0% · **Avance global:** 10.53%
**Gate:** approved

---

## 1. Executive Summary

Se puso la base de tooling Python reproducible del producto: proyecto `uv` con Python 3.12 pinned, `pyproject.toml` completo (ruff, mypy strict, pytest+cobertura ≥90%, pre-commit, pip-audit), lockfile versionado, esqueleto hexagonal de `src/` (PRD §9), entry point testeado, hooks pre-commit, workflow CI (quality + security + docker) y Dockerfile reproducible. Todo verde: lint, format, typing, tests 2/2, cobertura 100%, pre-commit 8/8, imagen Docker ejecuta y devuelve 0. La Dependency Proposal DP-002 quedó APPROVED. Falta el UAT y la aprobación humana del gate.

## 2. Objetivo

Poner la fundación de proyecto Python (uv, pyproject, lint, formatting, typing, pytest, coverage, pre-commit, CI inicial, Dockerfile inicial) y la estructura hexagonal de `src/` (PRD §79 Fase 01), sin adelantar lógica de dominio/API/DB.

## 3. Scope

- Estructura hexagonal `src/{domain,application,infrastructure,interfaces}` + `main.py`/`version.py`.
- `uv` como gestor; `uv.lock` versionado; Python 3.12 (`.python-version`).
- `pyproject.toml` completo (build hatchling, pytest markers, coverage, ruff, mypy strict).
- ruff check + format verdes; mypy strict verde.
- pytest operativo + coverage gate `--cov=src --cov-branch --cov-fail-under=90` (100% alcanzado).
- pre-commit hooks (ruff, whitespace/eof/yaml/large-files/private-key, mypy local).
- CI GitHub Actions (quality: lint+typing+tests+coverage; security: gitleaks+pip-audit; docker build).
- Dockerfile reproducible (`python:3.12-slim`) + `.dockerignore`.
- README actualizado con estructura y comandos de desarrollo.

## 4. Out of Scope

FastAPI, health/readiness endpoint, PostgreSQL/pgvector, SQLAlchemy/Alembic y cualquier lógica de dominio, market data o ejecución: **Fase 02+**. El paso "API health" del E2E del PRD (Fase 01) queda diferido a Fase 02 (FastAPI). El producto no tiene dependencias de runtime aún (`dependencies = []`).

## 5. Arquitectura antes/después

**Antes:** solo el arnés de gobernanza (`harness/`, `.opencode/skills/`, docs) y su propio `harness/pyproject.toml`. Sin código de producto.
**Después:** `src/` (src-layout: `src` es raíz de fuentes, módulos de nivel superior `main.py`/`version.py` y paquetes de capa `domain`, `application`, `infrastructure`, `interfaces`) + `tests/` + tooling raíz (`pyproject.toml`, `uv.lock`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `Dockerfile`, `.dockerignore`). Regla de dependencias: `domain ← application ← interfaces`, `infrastructure` implementa puertos (solo esqueleto por ahora).

## 6. Archivos creados

`pyproject.toml`, `uv.lock`, `.python-version`, `.pre-commit-config.yaml`, `Dockerfile`, `.dockerignore`, `.github/workflows/ci.yml`, `src/**` (25 archivos: main.py, version.py + 23 `__init__.py` de capas), `tests/test_main.py`, `docs/phases/01/*` (DP-002 + evidence×12), `docs/superpowers/plans/2026-08-23-phase-01-python-foundation.md`, `docs/uat/phase-01-uat.md`, `docs/phases/phase-01-report.md`.

## 7. Archivos modificados

`README.md` (estado, estructura con `src/`, sección de desarrollo del producto). `harness/state/progress.yaml` solo vía `progress.py` (fase 01 → in_progress → entregables done).

## 8. Dependencias

DP-002 **APPROVED** (2026-08-23): dev-deps `pytest≥8.3`, `pytest-cov≥5.0`, `ruff≥0.8`, `mypy≥1.11`, `pre-commit≥4.0`, `pip-audit≥2.7` + imagen `python:3.12-slim`. Resueltas: ruff 0.16.4, mypy 2.3.1, pytest 9.1.1, pytest-cov 7.1.0, pre-commit 4.6.2, pip-audit 2.10.1. Runtime del producto: **sin dependencias** aún.

## 9. Configuración

`pyproject.toml` ([project], [dependency-groups].dev, [build-system] hatchling, [tool.hatch.build.targets.wheel] packages con prefijo `src/`, [tool.pytest.ini_options] markers unit/integration/e2e, [tool.coverage.run] source=branch, [tool.coverage.report] fail_under=90, [tool.ruff] line-length 100 / target py312 / include py+pyi, [tool.mypy] strict). `.python-version` = 3.12. `.pre-commit-config.yaml` con `exclude` de docs/harness/.opencode/dist/build.

## 10. Comandos exactos (verificados)

```bash
uv sync                                                              # crea .venv + uv.lock
uv run ruff check .                                                  # exit=0
uv run ruff format --check .                                         # exit=0
uv run mypy src tests                                                # exit=0 (strict)
uv run pytest --cov=src --cov-branch --cov-fail-under=90             # 2 passed · 100%
uv run pre-commit install && uv run pre-commit run --all-files       # exit=0
uv run pip-audit                                                     # 0 vulnerabilidades
sudo docker build -t self-evaluating-trading-agent:dev .             # exit=0
sudo docker run --rm self-evaluating-trading-agent:dev               # "self-evaluating-trading-agent 0.1.0"
# E2E: git write-tree + git archive -> /tmp/opencode/... ; uv sync --frozen ; pytest (100%)
```

## 11. Rutas

`src/` (código), `tests/`, `docs/phases/01/evidence/` (12 logs + coverage.json), `.github/workflows/ci.yml`, `docs/phases/01/DP-002-*.md`, `docs/superpowers/plans/*.md`.

## 12. API endpoints

N/A (FastAPI llega en Fase 02).

## 13. Migraciones

N/A (Alembic llega en Fase 02).

## 14. Tests

| Nivel | Ejecutado | Resultado | Evidencia |
|---|---|---|---|
| Unit | ☑ 2 casos | PASS (2/2) | evidence/unit-tests.log |
| Integration | ☐ N/A fase 01 | — | — |
| E2E | ☑ clean-checkout → sync → tests | PASS | evidence/e2e.log |

## 15. Coverage

**100.00%** (branch) — objetivo ≥90% (PRD §70). `docs/phases/01/evidence/coverage.json`. Cubierto: `main.py` (100%), `version.py` (100%); los `__init__.py` vacíos no aportan líneas. Único hueco excluido con `# pragma: no cover`: el guard `if __name__ == "__main__"` (idiom estándar; el comportamiento de `main()` sí está testeado).

## 16. E2E

Snapshot fiel del estado a commitear (`git write-tree` + `git archive` → `/tmp/opencode/phase01-e2e.*`): `uv sync --frozen` (exit 0) → `uv run pytest --cov=src --cov-branch --cov-fail-under=90` (2 passed, 100%). Verifica lockfile reproducible y tests verdes en checkout limpio sin `.venv`.

## 17. UAT

- Checklist: `docs/uat/phase-01-uat.md`
- Veredicto: APPROVED

## 18. Evidencias

Índice: `docs/phases/01/evidence/log.md` — lint, format, typing, unit-tests, pre-commit, docker-build, docker-run, pip-audit, structure, uv-lock, ci-local, e2e + `coverage.json`.

## 19. Métricas

11/11 entregables done · 2 tests unit · 100% cobertura · 8/8 hooks pre-commit · 0 vulnerabilidades (pip-audit) · 49 paquetes resueltos en lock · imagen Docker ~ base python:3.12-slim.

## 20. Logs relevantes

`uv sync` resolvió 50 paquetes en ~1s con Python 3.12.13. Primera corrida de coverage dio 82% (guard `__main__` sin cubrir) → corregido con `# pragma: no cover` → 100%. pre-commit inicial tocó `docs/` (PRD + evidencia fase 00) → revertido con `git checkout` y corregido con `exclude` en la config.

## 21. Git diff

Todo el código de producto es nuevo (primer commit candidate con `src/`, `tests/`, tooling). Diff disponible a solicitud; se generará al preparar el Commit Candidate Report (`harness/templates/commit-candidate.md`).

## 22. Riesgos

- `mypy` resuelto a 2.3.1 (≥1.11): sintaxis `strict` compatible verificada.
- `sudo` necesario para docker localmente (usuario fuera del grupo `docker`): en CI el runner usa docker sin sudo. Documentado.
- Ruff 0.16 formatea `.md` por defecto → mitigado con `include = ["*.py", "*.pyi"]`.

## 23. Seguridad

Sin secretos (`.env` gitignored; `detect-private-key` en pre-commit; gitleaks en CI). `pip-audit`: 0 vulnerabilidades conocidas. Dependencias congeladas en `uv.lock`; CI usa `--frozen`. Imagen base oficial `python:3.12-slim` (no `latest`). `.dockerignore` excluye `.git`, `.venv`, `.env`, datasets, caches.

## 24. Deuda técnica

1. Dockerfile minimal (sin uv multi-stage): correcto porque no hay dependencias de runtime; se evoluciona en Fase 02 junto a FastAPI.
2. `[tool.hatch.build.targets.wheel] packages` con prefijo `src/` requerido por hatchling en src-layout (documentado).
3. CI no ejecutable hasta crear remoto GitHub + primer push autorizado; validado localmente con la misma secuencia.

## 25. Known Issues

- `uv add --dry-run` no existe en uv 0.11.25 (documentado en infra-control).
- Módulo de nivel superior `main` (src-layout literal del PRD §9): `python -m main` requiere `PYTHONPATH=src` (fijado en Dockerfile).
- Doble convención de rutas en docs/phases (phase-XX-report.md plano + XX/evidence/) asumida y documentada.

## 26. Rollback

Revertir/eliminar: `src/`, `tests/`, `pyproject.toml`, `uv.lock`, `.python-version`, `.pre-commit-config.yaml`, `.github/workflows/`, `Dockerfile`, `.dockerignore`; restaurar README; `uv run pre-commit uninstall`; `sudo docker rmi self-evaluating-trading-agent:dev`. Sin impacto externo (nada instalado fuera de `.venv/`; rollback DP-002 = borrar `.venv/` + `uv sync` de nuevo).

## 27. Competencias de Ingeniería de Software practicadas (PRD §80)

Python (entry point, tipado estricto) · Dependency Management (uv, lockfile versionado, dependency-groups) · CI (GitHub Actions: quality/security/docker) · Testing (TDD RED→GREEN, pytest, coverage branch) · Containers (Dockerfile reproducible, .dockerignore) · Architecture (layout hexagonal, src-layout) · Security basics (pip-audit, secret scanning, gitleaks) · Developer Experience (pre-commit, README).

## 28. Definition of Done

scope complete ☑ · tests PASS ☑ · integration N/A ☑ · E2E ☑ · UAT approved ☐ (usuario) · coverage ≥90% ☑ (100%) · CI green ☐ N/A sin remoto (secuencia local verde) · lint ☑ typing ☑ · documentation ☑ · evidence ☑ · diff reviewed ☐ (en Commit Candidate) · user approved ☐

## 29. Estado CI

Workflow `ci.yml` creado y validado localmente paso a paso (quality + security + docker, todos exit=0). No ejecutable en GitHub hasta que el usuario cree el remoto y se autorice el primer push (PRD §64-68).

## 30. Solicitud de aprobación

- [x] Presentado al usuario (junto con instructivo UAT `docs/uat/phase-01-uat.md`)
- **DECISIÓN DEL USUARIO:** ☑ APPROVED ☐ REJECTED
- Comentario: aprobado vía selector OpenCode (UAT APPROVED, gate approved)

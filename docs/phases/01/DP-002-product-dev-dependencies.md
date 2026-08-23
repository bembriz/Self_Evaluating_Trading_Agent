# Dependency Proposal — DP-002: Product dev-dependencies + Docker base image

> Obligatoria ANTES de instalar cualquier paquete, herramienta, imagen o servicio (PRD §11).
> Flujo: DISCOVER → PLAN/DRY-RUN → REPORT (este documento) → USER GATE → APPLY → VALIDATE → EVIDENCE.

## Propuesta

| Campo | Valor |
|---|---|
| Nombre | `pytest`, `pytest-cov`, `ruff`, `mypy`, `pre-commit`, `pip-audit` + imagen `python:3.12-slim` |
| Versión propuesta | `pytest>=8.3`, `pytest-cov>=5.0`, `ruff>=0.8`, `mypy>=1.11`, `pre-commit>=4.0`, `pip-audit>=2.7`; imagen `python:3.12-slim` |
| Tipo | ☑ paquete Python (dev) ☑ imagen Docker ☐ CLI ☐ servicio ☐ extensión/MCP |
| Comando de instalación | `uv sync` (instala dev-deps en `.venv`); `uv run pre-commit install` (hooks); `docker build` (pull `python:3.12-slim`) |

## Problema que resuelve

Fase 01 exige: lint (`ruff`), formatting (`ruff`), typing (`mypy`), tests (`pytest`+`pytest-cov`), coverage gate ≥90%, pre-commit hooks, CI (`pip-audit` para dependency audit) y Dockerfile reproducible (`python:3.12-slim`). Sin estas herramientas la fase no es verificable.

## Por qué es necesario

Son los tools estándar que el PRD (§10, §67, §70–71) y las skills (`python-uv`, `code-quality`, `testing-unit`, `cicd-github-actions`, `docker-standards`) fijan como obligatorios. La alternativa "no hacer nada" deja la Fase 01 sin gate mecánico verificable (sin coverage, sin typing, sin lint, sin CI).

## Alternativas consideradas

| Alternativa | Por qué se descarta |
|---|---|
| Reusar el `.venv` del arnés (`harness/.venv`) | El arnés es un proyecto separado (gobernanza); el producto debe tener su propio entorno reproducible y `uv.lock` propio. Mezclar ambos rompe aislamiento y la versionación del lock del producto. |
| `flake8`/`black`/`pyright` | El PRD y las skills ya fijan `ruff`+`mypy`; introducir un segundo linter/formatter duplica tooling (code-quality). |
| `uvx pip-audit` (sin declararlo) | Dejaría una herramienta fuera de `uv.lock`, no reproducible. Declararla como dev-dep es la opción limpia. |
| Imagen `python:latest` | `latest` no es reproducible (docker-standards). Se usa `python:3.12-slim` alineado al pin de Python 3.12. |

## Razón para NO implementarlo internamente

Linters, type-checkers, coverage y auditores de vulnerabilidades son herramientas maduras de ecosistema; reimplementarlas sería un sinsentido técnico y un riesgo (auditoría de CVEs propia no es viable).

## Impacto en arquitectura

Ninguno sobre el dominio. Solo añade `[dependency-groups].dev` al `pyproject.toml` del producto, `.venv/` (gitignored), `.pre-commit-config.yaml`, `.github/workflows/ci.yml` y `Dockerfile`. El runtime del producto sigue con `dependencies = []` (FastAPI, SQLAlchemy, etc. llegan en Fases 02+).

## Seguridad

- `ruff`, `mypy`, `pytest`, `pytest-cov`, `pre-commit`, `pip-audit`: todos MIT/Apache-2.0/BSD, alta adopción, mantenidos activamente (Astral/PyPA/mypy). Supply chain vía PyPI, resuelto y congelado en `uv.lock`.
- `python:3.12-slim`: imagen oficial de Python (Docker Official Image), firma/escaneo por el maintainer. No `latest`.
- `pip-audit` usa la base de datos OSV para CVEs de Python (misma fuente que los scanners habituales).
- Ninguna de estas herramientas toca secretos ni expone red.

## Impacto en licencia del proyecto

Sin cambios: todas son dev-dependencies MIT/Apache-2.0/BSD compatibles; no afectan la licencia del producto.

## Rollback

- Eliminar `[dependency-groups].dev` de `pyproject.toml` + borrar `.venv/` + re-ejecutar `uv sync`.
- `uv run pre-commit uninstall` + borrar `.pre-commit-config.yaml`.
- Borrar `Dockerfile`/`.dockerignore`; la imagen local se elimina con `docker rmi self-evaluating-trading-agent:dev` (no `docker system prune`, que está deny).

## DRY-RUN ejecutado (pre-gate)

```bash
# DISCOVER (solo lectura) ya ejecutado el 2026-08-23:
uv --version                       # uv 0.11.25
python3 --version                  # 3.14.4 (sistema) — NO se usará; se pin 3.12
uv python list                     # cpython-3.12.13 ya disponible vía uv (sin descarga nueva)
docker --version                   # Docker 29.7.2
which pre-commit gitleaks          # no instalados (pre-commit va como dev-dep; gitleaks solo en CI)
```

---

**DECISIÓN DEL USUARIO:** ☑ APPROVED ☐ REJECTED — Fecha: 2026-08-23 Firma/comentario: aprobado vía selector OpenCode (gate DP-002)

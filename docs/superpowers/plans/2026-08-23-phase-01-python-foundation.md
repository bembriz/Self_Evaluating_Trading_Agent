# Phase 01 — Python Project Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poner la base de tooling Python reproducible del producto (uv, pyproject, ruff, mypy, pytest+cobertura, pre-commit, CI y Dockerfile) sobre la estructura hexagonal de `src/`.

**Architecture:** Monolito modular hexagonal (PRD §8–9). En esta fase solo se crea el esqueleto de paquetes `src/{domain,application,infrastructure,interfaces}` y un `main.py` mínimo y testeable. Ningún framework web, DB ni lógica de dominio aún: llegan en Fases 02+.

**Tech Stack:** Python 3.12 (pinned vía `.python-version`), uv 0.11, ruff, mypy, pytest + pytest-cov, pre-commit, GitHub Actions, Docker.

## Global Constraints

- Python `==3.12` (pinned; el arnés usa `py312` y el sistema tiene 3.14 — NO usar 3.14).
- `uv.lock` versionado; jamás `requirements.txt` como fuente primaria.
- Line length ruff: `100`; target-version `py312`.
- Coverage gate: `--cov=src --cov-branch --cov-fail-under=90` (PRD §70).
- mypy `strict = true` sobre `src` + `tests`.
- NINGUNA instalación sin DP-002 APPROVED (PRD §11). `uv add`/`uv sync`/`pre-commit install`/`docker build` están gated.
- Secretos fuera del repo (`.env` gitignored; `detect-private-key` en pre-commit; gitleaks en CI).
- Sin commits/push/merge sin autorización explícita (PRD §65–66).
- Estructura de capas (regla dura): `domain ← application ← interfaces`, `infrastructure` implementa puertos. En esta fase solo paquetes vacíos.
- No construir lógica de dominio/API/DB en esta fase (out of scope → Fases 02+).

---

### Task 1: Dependency Proposal DP-002 + USER GATE

**Files:**
- Create: `docs/phases/01/DP-002-product-dev-dependencies.md`

**Interfaces:**
- Produces: decisión APPROVED del usuario que desbloquea todos los `uv sync`/`pre-commit install`/`docker build` de las tareas siguientes.

- [ ] **Step 1: Escribir la proposal** (ya ejecutado DISCOVER: `uv 0.11.25`, `python 3.14.4` sistema + `3.12.13` vía uv, `docker 29.7.2`, sin `pre-commit`/`gitleaks`).

Contenido mínimo (plantilla `harness/templates/dependency-proposal.md`):
- Paquete Python (dev): `pytest`, `pytest-cov`, `ruff`, `mypy`, `pre-commit`, `pip-audit`.
- Imagen Docker: `python:3.12-slim`.
- Alternativas, seguridad/licencia, rollback, DRY-RUN ya ejecutado.

- [ ] **Step 2: Presentar DP-002 al usuario y esperar APPROVED/REJECTED.**

Esperado: el usuario escribe APPROVED (o usa el selector). Si REJECTED → ajustar y re-presentar.

---

### Task 2: pyproject + .python-version + uv.lock

**Files:**
- Create: `pyproject.toml`, `.python-version`
- Create: `uv.lock` (generado por `uv sync`)

**Interfaces:**
- Consumes: DP-002 APPROVED (Task 1).
- Produces: `uv.lock` versionado y `.venv/` con las dev-deps instaladas. Todos los comandos `uv run ...` siguientes dependen de esto.

- [ ] **Step 1: Escribir `.python-version`**

```text
3.12
```

- [ ] **Step 2: Escribir `pyproject.toml`**

```toml
[project]
name = "self-evaluating-trading-agent"
version = "0.1.0"
description = "Self-Evaluating Trading Agent — ETH/USDT spot, long-only"
readme = "README.md"
requires-python = ">=3.12,<3.13"
dependencies = []

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-cov>=5.0",
    "ruff>=0.8",
    "mypy>=1.11",
    "pre-commit>=4.0",
    "pip-audit>=2.7",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
markers = [
    "unit: unit tests (dominio puro)",
    "integration: integration tests",
    "e2e: end-to-end tests",
]

[tool.coverage.run]
source = ["src"]
branch = true

[tool.coverage.report]
fail_under = 90
show_missing = true

[tool.ruff]
line-length = 100
target-version = "py312"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
files = ["src", "tests"]
```

- [ ] **Step 3: Resolver y sincronizar (crea `uv.lock` + `.venv`)**

Run: `uv sync`
Expected: exit 0, `uv.lock` creado, `.venv/` con las dev-deps.

- [ ] **Step 4: Verificar versiones instaladas**

Run: `uv run ruff --version && uv run mypy --version && uv run pytest --version`
Expected: exit 0, versiones ≥ las mínimas declaradas.

- [ ] **Step 5: Commit** *(solo con autorización del usuario)*

```bash
git add pyproject.toml .python-version uv.lock
git commit -m "feat(phase-01): pyproject, python 3.12 pinned y uv.lock"
```

---

### Task 3: Esqueleto hexagonal src/ + main.py (TDD)

**Files:**
- Create: `src/__init__.py`, `src/main.py`
- Create: paquetes vacíos `src/domain/{market,trading,portfolio,risk,evaluation,memory,experiments}/__init__.py`, `src/application/{services,commands,queries,ports}/__init__.py`, `src/infrastructure/{bybit,database,llm,embeddings,observability,execution}/__init__.py`, `src/interfaces/{api,web,cli}/__init__.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Produces: `src.main.main(argv: list[str] | None = None) -> int` (retorna 0, imprime identidad+versión) y `src.__version__` (semver). Cobertura 100% de `src/` en esta fase.

- [ ] **Step 1: Escribir el test que falla**

```python
import re

import src
from src.main import main


def test_version_is_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", src.__version__) is not None


def test_main_returns_zero(capsys) -> None:  # noqa: ANN001
    assert main() == 0
    out = capsys.readouterr().out
    assert "self-evaluating-trading-agent" in out
    assert src.__version__ in out
```

- [ ] **Step 2: Ejecutar el test para confirmar que falla**

Run: `uv run pytest tests/test_main.py -v`
Expected: FAIL (module `src` no existe / no hay `main`).

- [ ] **Step 3: Crear `src/__init__.py`**

```python
"""Self-Evaluating Trading Agent."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Crear `src/main.py`**

```python
"""Entry point of the Self-Evaluating Trading Agent."""

from __future__ import annotations

from src import __version__


def main(argv: list[str] | None = None) -> int:
    """Print identity and return success.

    `argv` is reserved for subcommands in later phases.
    """
    del argv
    print(f"self-evaluating-trading-agent {__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Crear el esqueleto de paquetes vacíos**

Run (un solo comando, solo crea `__init__.py` vacíos):

```bash
for d in domain/market domain/trading domain/portfolio domain/risk \
         domain/evaluation domain/memory domain/experiments \
         application/services application/commands application/queries application/ports \
         infrastructure/bybit infrastructure/database infrastructure/llm \
         infrastructure/embeddings infrastructure/observability infrastructure/execution \
         interfaces/api interfaces/web interfaces/cli; do
  mkdir -p "src/$d" && : > "src/$d/__init__.py"
done
```

- [ ] **Step 6: Ejecutar el test para confirmar que pasa**

Run: `uv run pytest tests/test_main.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit** *(solo con autorización)*

```bash
git add src tests/test_main.py
git commit -m "feat(phase-01): esqueleto hexagonal src/ y entry point main.py"
```

---

### Task 4: ruff — lint y format verdes

**Files:**
- Modify: `pyproject.toml` (ya contiene `[tool.ruff]` en Task 2; verificar)

**Interfaces:**
- Consumes: `pyproject.toml` (Task 2).
- Produce: `ruff check .` y `ruff format --check .` con exit 0.

- [ ] **Step 1: Ejecutar ruff check**

Run: `uv run ruff check .`
Expected: exit 0 (o corregir hallazgos). Si hay errores de import (I) en el esqueleto, se auto-corrigen con `ruff check --fix`.

- [ ] **Step 2: Ejecutar ruff format --check**

Run: `uv run ruff format --check .`
Expected: exit 0. Si no, `uv run ruff format .` y re-chequear.

- [ ] **Step 3: Registrar evidencia**

Run:
```bash
harness/scripts/evidence.sh 01 lint -- uv run ruff check .
harness/scripts/evidence.sh 01 format -- uv run ruff format --check .
```

- [ ] **Step 4: Commit** *(solo con autorización)*

---

### Task 5: mypy verde

**Files:**
- Modify: `pyproject.toml` (`[tool.mypy]` ya presente; ajustar si `strict` produce ruido no deseado en `tests`)

**Interfaces:**
- Consumes: Task 3 (código + tests).
- Produce: `uv run mypy src tests` exit 0.

- [ ] **Step 1: Ejecutar mypy**

Run: `uv run mypy src tests`
Expected: exit 0 (Success: no issues). Si `strict` falla en `tests` por anotaciones de fixtures, usar `# noqa: ANN001`/`# type: ignore[arg-type]` de forma acotada o tipar correctamente.

- [ ] **Step 2: Registrar evidencia**

Run: `harness/scripts/evidence.sh 01 typing -- uv run mypy src tests`

- [ ] **Step 3: Commit** *(solo con autorización)*

---

### Task 6: pytest + coverage gate ≥90%

**Files:**
- Modify: `pyproject.toml` (`[tool.pytest]`, `[tool.coverage]` ya presentes)
- Create: `docs/phases/01/evidence/coverage.json` (artefacto)

**Interfaces:**
- Consumes: Task 3 (tests).
- Produce: suite verde y `coverage.json` con `totals.percent_covered >= 90`.

- [ ] **Step 1: Ejecutar la suite con coverage**

Run:
```bash
uv run pytest --cov=src --cov-branch --cov-fail-under=90 \
  --cov-report=term --cov-report=json:docs/phases/01/evidence/coverage.json
```
Expected: exit 0, cobertura ≥ 90% (debería ser 100% en esta fase).

- [ ] **Step 2: Registrar evidencia de la suite**

Run:
```bash
harness/scripts/evidence.sh 01 unit-tests -- uv run pytest --cov=src --cov-branch --cov-fail-under=90
```

- [ ] **Step 3: Commit** *(solo con autorización)*

---

### Task 7: pre-commit hooks

**Files:**
- Create: `.pre-commit-config.yaml`

**Interfaces:**
- Consumes: DP-002 (pre-commit como dev-dep).
- Produce: `.git/hooks/pre-commit` instalado; `pre-commit run --all-files` verde.

- [ ] **Step 1: Escribir `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.6
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
        args: ["--maxkb=500"]
      - id: detect-private-key
  - repo: local
    hooks:
      - id: mypy
        name: mypy
        entry: uv run mypy src tests
        language: system
        types: [python]
        pass_filenames: false
```

- [ ] **Step 2: Instalar hooks**

Run: `uv run pre-commit install`
Expected: exit 0, `.git/hooks/pre-commit` creado.

- [ ] **Step 3: Ejecutar todos los hooks**

Run: `uv run pre-commit run --all-files`
Expected: exit 0 (todos los hooks PASS).

- [ ] **Step 4: Registrar evidencia**

Run: `harness/scripts/evidence.sh 01 pre-commit -- uv run pre-commit run --all-files`

- [ ] **Step 5: Commit** *(solo con autorización)*

---

### Task 8: CI inicial (GitHub Actions)

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: pyproject (Task 2), estructura+code (Task 3), Dockerfile (Task 9, pero el job `docker` puede existir desde ya).
- Produce: workflow que ejecuta lint + typing + tests/coverage + secret scanning + dependency audit + docker build.

- [ ] **Step 1: Escribir `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  quality:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
          enable-cache: true
      - run: uv sync --frozen
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy src tests
      - run: uv run pytest --cov=src --cov-branch --cov-fail-under=90

  security:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Secret scanning (gitleaks)
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
      - run: uv sync --frozen
      - name: Dependency audit (pip-audit)
        run: uv run pip-audit

  docker:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - name: Build image
        run: docker build -t self-evaluating-trading-agent:ci .
```

- [ ] **Step 2: Validar sintaxis YAML**

Run: `uv run pre-commit run check-yaml --all-files` (o `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`)
Expected: exit 0.

- [ ] **Step 3: Documentar en README que CI está listo y se valida localmente con la misma secuencia de comandos hasta el primer push autorizado.**

- [ ] **Step 4: Commit** *(solo con autorización)*

---

### Task 9: Dockerfile inicial

**Files:**
- Create: `Dockerfile`, `.dockerignore`

**Interfaces:**
- Consumes: DP-002 (imagen base `python:3.12-slim`).
- Produce: `docker build` exit 0 y contenedor que imprime la identidad y sale 0.

- [ ] **Step 1: Escribir `.dockerignore`**

```gitignore
.git
.venv
**/__pycache__
*.pyc
__pycache__/
docs
harness
datasets
data
*.log
.env
.env.*
.coverage
coverage.xml
htmlcov
.pytest_cache
.mypy_cache
.ruff_cache
.github
```

- [ ] **Step 2: Escribir `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY src ./src
COPY pyproject.toml ./

CMD ["python", "-m", "src.main"]
```

- [ ] **Step 3: Construir imagen**

Run: `docker build -t self-evaluating-trading-agent:dev .`
Expected: exit 0.

- [ ] **Step 4: Ejecutar contenedor**

Run: `docker run --rm self-evaluating-trading-agent:dev`
Expected: imprime `self-evaluating-trading-agent 0.1.0` y exit 0.

- [ ] **Step 5: Registrar evidencia**

Run:
```bash
harness/scripts/evidence.sh 01 docker-build -- docker build -t self-evaluating-trading-agent:dev .
harness/scripts/evidence.sh 01 docker-run -- docker run --rm self-evaluating-trading-agent:dev
```

- [ ] **Step 6: Commit** *(solo con autorización)*

---

### Task 10: README (instrucciones de desarrollo)

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: todo lo anterior.
- Produce: sección "Desarrollo" con los comandos canónicos.

- [ ] **Step 1: Añadir sección de desarrollo al README** con los comandos exactos:

```text
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest --cov=src --cov-branch --cov-fail-under=90
uv run pre-commit install
docker build -t self-evaluating-trading-agent:dev .
```

- [ ] **Step 2: Commit** *(solo con autorización)*

---

### Task 11: E2E — clone → uv sync → tests

**Files:**
- Create: `docs/phases/01/evidence/e2e.log` (artefacto)

**Interfaces:**
- Consumes: repo completo.
- Produce: evidencia de que un checkout limpio resuelve dependencias y pasa tests (PRD Fase 01 E2E). El paso "API health" es de Fase 02 (FastAPI) y queda documentado como out-of-scope.

- [ ] **Step 1: Clonar el repo a un dir temporal**

Run:
```bash
rm -rf /tmp/opencode/phase01-e2e && git clone . /tmp/opencode/phase01-e2e
```
Expected: exit 0.

- [ ] **Step 2: `uv sync` en el clon**

Run: `uv sync`
Workdir: `/tmp/opencode/phase01-e2e`
Expected: exit 0.

- [ ] **Step 3: `uv run pytest` en el clon**

Run: `uv run pytest --cov=src --cov-branch --cov-fail-under=90`
Workdir: `/tmp/opencode/phase01-e2e`
Expected: exit 0.

- [ ] **Step 4: Registrar evidencia E2E**

Run: `harness/scripts/evidence.sh 01 e2e -- bash -c '... secuencia clon+sync+tests ...'`

- [ ] **Step 5: Limpiar el clon temporal**

Run: `rm -rf /tmp/opencode/phase01-e2e`

---

### Task 12: Marcar entregables + gate_check + reporte

**Files:**
- Modify: `docs/phases/phase-01-report.md` (completar 30 secciones)
- Modify: `docs/uat/phase-01-uat.md` (checklist HITL)
- Modify: `harness/state/progress.yaml` (solo vía `progress.py`)

**Interfaces:**
- Consumes: Tasks 2–11 completas.
- Produce: `gate_check.py --phase 01` con 0 FAIL; reporte completo; UAT entregado al usuario.

- [ ] **Step 1: Marcar cada entregable con evidencia** (un `mark-done` por entregable con su ruta de evidencia):

```bash
python3 harness/scripts/progress.py mark-done --phase 01 --deliverable estructura-del-proyecto --evidence docs/phases/01/evidence/log.md
# ... repetir para los 11 entregables con su evidencia correspondiente
```

- [ ] **Step 2: Ejecutar gate_check**

Run: `python3 harness/scripts/gate_check.py --phase 01`
Expected: 0 FAIL (los MANUAL — UAT/aprobación — se resuelven con el usuario).

- [ ] **Step 3: Completar el reporte de fase** (30 secciones) con datos reales de evidencia.

- [ ] **Step 4: Completar el UAT checklist** con pasos ejecutables por el usuario.

- [ ] **Step 5: Presentar reporte + UAT al usuario y esperar veredicto UAT + gate-approve.**

- [ ] **Step 6: Tras APPROVED, registrar gate** (`progress.py gate-approve --phase 01`) y cerrar la fase.

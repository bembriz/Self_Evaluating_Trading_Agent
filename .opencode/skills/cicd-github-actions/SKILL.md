---
name: cicd-github-actions
description: Usar al crear o modificar workflows de GitHub Actions, definir jobs de CI (lint/typing/tests/migraciones/secrets/build), configurar secrets del repo, o depurar pipelines rojos
---

# cicd-github-actions — CI en GitHub Actions

## Propósito

CI verde como requisito de gate (PRD §77): pipeline reproducible que ejecuta exactamente lo que exige el proyecto, sin secretos en claro y sin pasos manuales ocultos.

## Cuándo usar

- Fase 01 (CI inicial) y cualquier workflow nuevo posterior.
- Cuando CI falla en GitHub pero pasa local (o viceversa).
- Al añadir servicios a CI (postgres/pgvector) para integration tests.

**Cuándo NO:** ejecuciones locales (usa evidence.sh); CD cloud (fuera de scope hasta Fase 18+).

## Pipeline estándar del producto (PRD §67)

```yaml
jobs:
  quality:
    steps:
      - uv sync --frozen
      - uv run ruff check .
      - uv run ruff format --check .
      - uv run mypy src tests
      - uv run pytest --cov=src --cov-branch --cov-fail-under=90
  migrations:
    services: [postgres+pgvector]   # job separado con servicio real
    steps:
      - uv run alembic upgrade head
      - uv run alembic downgrade base && upgrade head   # roundtrip
  security:
    steps:
      - secret scanning (gitleaks o equivalente autorizado)
      - dependency audit
  docker:
    steps:
      - docker build (imagen reproducible)
```

## Reglas duras

- Secrets SOLO vía GitHub Actions Secrets; jamás en YAML ni logs (security-secrets).
- `--frozen` siempre en sync: CI nunca resuelve versiones nuevas.
- No deshabilitar steps para "arreglar" el pipeline (PRD §84 regla 7-8): si un gate es correcto, se arregla el código.
- Workflows versionados; cambios de CI = commit candidate normal.
- Sin remoto aún: workflows se crean listos y se validan localmente (misma secuencia de comandos) hasta el primer push autorizado.

## Checklist de workflow nuevo

1. Trigger explícito (push/PR a main + ramas).
2. Cache de uv correcto (key con hash de lock).
3. Servicios con healthcheck antes de tests.
4. Timeout y fail-fast sensatos.
5. Probado localmente paso a paso antes de push.

## Errores comunes

- CI verde local / rojo remoto por versión de Python distinta → fijar versiones.
- Secretos impresos en logs de error.
- Jobs paralelos que compiten por el mismo servicio.

## Referencias

- PRD §67–68. Skills: infra-control (nuevas tools), security-secrets, flujo-commits.

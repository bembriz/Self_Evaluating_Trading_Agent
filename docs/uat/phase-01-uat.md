# UAT — Fase 01: Python Project Foundation

> Prueba de aceptación de usuario (HITL). El agente NO puede aprobar UAT.
> Ejecuta los pasos tal cual y completa "Resultado observado" y el veredicto final.

## Precondiciones

| # | Precondición | Verificada ☐ |
|---|---|---|
| 1 | `uv` instalado (≥0.11) y `uv --version` funciona | ☐ |
| 2 | Python 3.12 disponible (uv lo gestiona vía `.python-version`) | ☐ |
| 3 | Docker instalado (`docker --version`); si el usuario no está en el grupo `docker`, usar `sudo docker` | ☐ |
| 4 | Terminal en la raíz del repositorio | ☐ |

## Entradas / Datos

Ninguna. La fase no requiere credenciales ni datos externos.

## Pasos

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | `uv sync` | Instala dependencias en `.venv`; crea/verifica `uv.lock`; exit 0 |
| 2 | `uv run pytest --cov=src --cov-branch --cov-fail-under=90` | `2 passed` y "Total coverage: 100.00%" |
| 3 | `uv run ruff check .` | "All checks passed!" |
| 4 | `uv run ruff format --check .` | "N files already formatted" (sin cambios pendientes) |
| 5 | `uv run mypy src tests` | "Success: no issues found" |
| 6 | `uv run pre-commit run --all-files` | 8 hooks Passed / Skipped, exit 0 |
| 7 | `sudo docker build -t self-evaluating-trading-agent:dev .` (o `docker` si estás en el grupo) | exit 0, imagen construida |
| 8 | `sudo docker run --rm self-evaluating-trading-agent:dev` | Imprime `self-evaluating-trading-agent 0.1.0` |
| 9 | `uv run pip-audit` | "No known vulnerabilities found" |
| 10 | Revisar `src/` (tiene `domain/`, `application/`, `infrastructure/`, `interfaces/`, `main.py`, `version.py`) | Estructura hexagonal presente |

## Evidencia a adjuntar

Salida de cada comando (pasos 1–9) y captura del árbol de `src/` (paso 10).

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
| 9 | | | |
| 10 | | | |

## Incidencias encontradas

> Desviaciones, errores o comportamientos inesperados.

---

## VEREDICTO UAT: APPROVED
<!-- Sustituir PENDING por APPROVED o REJECTED. gate_check exige el veredicto APPROVED visible (los comentarios HTML no cuentan) al check uat-approved -->
Decisor: usuario  Fecha: 2026-08-23
Comentario: aprobado vía selector OpenCode

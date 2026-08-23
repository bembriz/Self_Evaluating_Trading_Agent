---
name: flujo-commits
description: Usar cuando se vaya a preparar, solicitar o ejecutar un commit/push/merge/tag/release en este repositorio, cuando el usuario pida autorización de commit, o al generar el Commit Candidate Report (PRD §65-66)
---

# flujo-commits — Git con autorización obligatoria

## Propósito

Garantizar que **ningún commit, push, merge, tag o release ocurra sin aprobación humana explícita**, y que cada solicitud venga acompañada del Commit Candidate Report completo (PRD §66).

## Cuándo usar

- Antes de pedir autorización de cualquier `git commit`.
- Al preparar ramas (`feature/*`, `fix/*`, `chore/*`) y staging.
- Cuando el usuario pregunte "¿qué cambiarías en este commit?".
- Tras completar una unidad de trabajo atómica lista para historial.

**Cuándo NO usar:** operaciones de solo lectura (status/diff/log) o creación de ramas sin commit.

## Entradas → Salidas

- **Entradas:** cambios staged, suites ejecutadas, cobertura exacta, diff disponible.
- **Salidas:** `harness/templates/commit-candidate.md` completado + mensaje propuesto; tras APPROVED, el commit ejecutado.

## Checklist (en orden, sin saltos)

1. Verificar rama correcta y base actualizada (`git status`, `git log --oneline -5`).
2. `git add` selectivo: solo archivos del cambio atómico (revisar `git diff --cached`).
3. Ejecutar calidad completa y registrar evidencia con `harness/scripts/evidence.sh`:
   `ruff check`, `ruff format --check`, `mypy` (Fase 01+), `pytest --cov`.
4. Escanear diff buscando secretos/credenciales/rutas `.env` (debe ser cero).
5. Blast radius con codebase-memory-mcp: `detect_changes` + `check_index_coverage`
   (skill `codebase-memory-mcp`); registrar símbolos afectados en el reporte.
6. Completar TODAS las secciones de `harness/templates/commit-candidate.md`.
7. Presentar resumen ejecutivo al usuario y **esperar decisión explícita**.
8. Solo con "APPROVED": ejecutar el commit con el mensaje propuesto.
9. Tras el commit: re-indexar el grafo (`index_repository`) y verificar cobertura de los
   archivos tocados, para mantener la memoria estructural en paralelo al historial.

## Permitido / Prohibido

| Permitido sin pedir | Prohibido sin USER APPROVAL |
|---|---|
| crear ramas, editar, testear | `git commit` |
| `git add`, generar diffs/reportes | `git push` |
| `git status/log/diff/stash` | `merge`, `tag`, release |

El enforcement técnico (`opencode.json`) marca los prohibidos como `ask`: si aparece la petición de permiso, es señal de que el flujo llegó al punto correcto de decisión humana.

## Errores comunes

- Commits "para guardar trabajo" (WIP): no; usa ramas y commits atómicos coherentes.
- Mensajes vagos ("fixes", "cambios"): el mensaje propuesto sigue `type(scope): descripción` con cuerpo explicativo.
- Pedir commit antes de tener cobertura/lint verdes: rechazo garantizado.

## Referencias

- PRD §64–66 (estrategia y reporte). Plantilla: `harness/templates/commit-candidate.md`.
- Globales: git-safety-guardrails, superpowers:requesting-code-review, security-secrets.

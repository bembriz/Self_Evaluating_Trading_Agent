# Commit Candidate 002 — Phase 23 M0-II (GastosIA Backup + Restore Test)

> **Estado:** PREPARADO — **NO COMMIT** (requiere autorización explícica del usuario, PRD §64–66 / skill `flujo-commits`)

## 1. Objetivo

Registrar en el repositorio el entregable M0-II de la Fase 23: reporte de backup+restore de GastosIA, sus 24 evidencias auditables y la marca de completado en el ledger (generada exclusivamente por `progress.py`).

## 2. Rama y base

| Campo | Valor |
|---|---|
| Rama | `medalion` |
| HEAD actual (base) | `df907c5d12fce6c0aee90adac5ae88e164633b5a` (= `origin/medalion`) |
| `origin/main` | `962c971249fd34671d0ace323100aac984fd44ff` (sin cambios) |
| Tipo | commit único, atómico, sin amend, sin push |

## 3. Archivos (29 tras añadir este candidato)

**Modificados (2):**

| Archivo | Diff |
|---|---|
| `docs/phases/23/evidence/log.md` | +24 (entradas `m0ii-*`) |
| `harness/state/progress.yaml` | +8/−2 (solo vía `progress.py mark-done` para `23/m0ii-gastosia-rescue`) |

**Nuevos (27):**

- `docs/phases/23/m0-ii-gastosia-rescue.md` (reporte del entregable)
- `docs/phases/23/commit-candidate-002.md` (este documento)
- `docs/phases/23/evidence/m0ii-*.log` × 24 (crudos, inmutables; exits: 0 salvo `m0ii-13`=1 y `m0ii-13b`=1 documentados como artefactos corregidos)

**NO se toca:** `src/`, `deploy/`, `config/`, `splits/`, `holdout/`, `AGENTS.md` global, certificación, compose de producción, `docker-compose*`.

## 4. Arquitectura afectada

Ninguna. Documentación y ledger de harness exclusivamente (0 líneas de código de producto). Infraestructura lenovosrv no mutada por este commit (el backup vive en `/srv/backup-before-medallion/gastosia`, fuera del repo).

## 5. Tests y calidad

| Verificación | Resultado |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 309 files already formatted |
| `mypy` / suites pytest | Sin cambios de código → sin re-ejecución obligatoria; referencia: M0-I (`m0ii` no modifica `src/`); deuda preexistente documentada (2 tests `test_gen_pdf.py` requieren Dependency Proposal) |
| Escaneo de secretos en archivos a commitear | `SECRET_HITS=0` (patrones Google/OpenAI/GitHub/JWT/private-key) |
| `git diff --check` | pendiente de ejecución en staging (espacios en evidencia raw intencionales: salidas de comandos; si `--check` reporta trailing whitespace en logs crudos, NO se editan — inmutabilidad de evidencia) |

## 6. Seguridad

- Evidencia revisada: **0 secretos impresos** (env de app solo claves; passwords vía sustitución de shell jamás registrada)
- El backup remoto contiene secretos reales (`gastos-ia-app.env` 600 + `cred/`): **fuera del repo**, solo en lenovosrv
- Ningún archivo sensible nuevo para git (`.env` de repo intocado)

## 7. Riesgos y deuda

- **Riesgo bajo:** commit documental; rollback = revert del commit
- Deuda: decisión pendiente de cifrado del backup si sale de lenovosrv (M1); total bytes del backup documentados en reporte/manifest
- `READY_FOR_M1_PREPARATION=YES` pero M1 **bloqueado** por regla global de gobernanza

## 8. Mensaje propuesto

```
docs(phase-23): record gastosia backup and restore test
```

Body sugerido (opcional, a aprobación del usuario):

```
M0-II deliverable: full GastosIA backup (20.82 GiB, 5234 files
SHA-256 verified) + isolated restore test (pg_restore 10/10 tables,
row counts match, files + DB hashes match, app boots on temp DB),
24 evidence logs, ledger updated via progress.py.
```

## 9. Verificación post-commit (a ejecutar tras autorización)

`git status --short` limpio · `git rev-parse HEAD^` = `df907c5…` · 1 commit adelante · re-index codebase-memory y `check_index_coverage` sobre los paths tocados (§4.13).

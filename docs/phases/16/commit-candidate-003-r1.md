# Commit Candidate Report — R1.0 (Remediación 1)

- **Fecha:** 2026-09-02
- **Rama:** `feature/paper-regime-certification` (worktree `/tmp/opencode/paper-regime-certification`)
- **Base:** `ef08869` `feat(phase-16): Paper Trading Certification + periodic reports`

## Objetivo
Cerrar en un commit el avance de Fase 16 previo al despliegue de la Remediación 1:
1. **Confirmación de regímenes de mercado** en el paper runner (`regime_confirmation.py` + integración en `PaperRunner` y CLI) con evidencia estructurada, deduplicada y sin lookahead.
2. **Endurecer el gate de certificación** (`harness/scripts/paper_certification.py`): solo cuenta evidencia estructurada válida y regímenes distintos.
3. **Alinear fixtures de integración de memoria** con `pgvector vector(384)` (DP-005 local-postgres).
4. **Saneado S1:** eliminar la credencial en texto plano embebida en evidencia de despliegue (auditoría: `docs/audits/2026-09-02-*.md`, sección S1).

## Archivos

**Modificados (10):**
- `docs/phases/16/evidence/deploy-applied-lenosrv.log` (redactado)
- `docs/phases/16/evidence/deploy-validate-live-klines.log` (redactado)
- `docs/phases/16/evidence/log.md` (entradas redactadas + nuevas)
- `harness/scripts/paper_certification.py`
- `harness/tests/test_paper_certification.py`
- `src/application/services/paper_runner.py`
- `src/interfaces/cli/paper_runner.py`
- `tests/integration/test_memory_repository.py`
- `tests/test_cli_paper_runner.py`
- `tests/test_paper_runner.py`

**Nuevos:**
- `src/application/services/regime_confirmation.py`
- `tests/test_regime_confirmation.py`
- `docs/phases/16/DP-005-local-postgres-integration-tests.md`
- `docs/phases/16/evidence/{dp-005-postgres-apply,dp-005-postgres-health,memory-embedding-format,memory-embedding-full-suite,memory-embedding-integration-tests,memory-embedding-ruff,paper-regime-final-tests,paper-regime-focused-tests,paper-regime-format,paper-regime-full-suite,paper-regime-gate-check,paper-regime-integration-tests,paper-regime-mypy,paper-regime-ruff}.log`
- `docs/superpowers/plans/2026-09-02-memory-integration-embedding-dimension.md`
- `docs/superpowers/specs/2026-09-02-memory-integration-embedding-dimension-design.md`

**No incluidos (docs aparte):** `docs/audits/2026-09-02-auditoria-lenosrv-vs-prd-3-1.md`, `docs/phases/16/remediation-01-sin-llm-7-dias.md`, `docs/phases/16/remediation-02-llm-7-dias.md` (se versionarán en un commit de documentación posterior).

## Diff
Referencia íntegra: `git -C /tmp/opencode/paper-regime-certification diff` + untracked list (`git status --porcelain`). Resumen: 433 insertions, 27 deletions en tracked; +~450 líneas nuevas (tracker + tests).

## Arquitectura afectada
- `src/application/services/paper_runner.py`: `PaperRunner` mantiene un `RegimeConfirmationTracker` por símbolo, integra régimen confirmado en reportes/estado de certificación; expone `regime_evidence()`/`rejected_regime_candidates`.
- `src/interfaces/cli/paper_runner.py`: escritura de reportes periódicos + `certification-state.json`.
- `harness/scripts/paper_certification.py`: validación estricta de evidencia (solo estructura válida; regímenes distintos).
- **Sin cambios** en Risk Engine, portfolio, dominio de trading, LLM ni migraciones.

## Tests (ejecutados hoy, worktree)
- `pytest` (suite completa, incl. integración con PostgreSQL local): **440 passed, 1 skipped**.
- `pytest --cov=src --cov-branch`: **TOTAL 94.55%** (requerido ≥90 alcanzado).
- Cobertura harness (evidencia previa): `paper-certification-harness-coverage.log` (fase 16).

## Calidad
- `ruff check .` → All checks passed
- `ruff format --check .` → 231 files already formatted
- `mypy src tests` → Success, no issues found in 203 source files

## Seguridad
- Escaneo de credenciales en todo el diff: **limpio** tras redactar S1 (`[REDACTED]` en los 3 archivos de evidencia).
- **Pendiente de acción del usuario (R1.6):** rotar el password sudo de `lenovosrv`. El saneado elimina la copia en el repo, no invalida la credencial ya usada.

## Blast radius
- `detect_changes` (base `feature/phase-08-llm-decision-agent`, merge_base `ef08869`): 27 archivos cambiados, 68 símbolos en el radio de impacto (src/application 19, src/domain 21, src/infrastructure 7, harness 1, tests 7+…). Sin llamadores externos HIGH fuera de los módulos tocados.
- `check_index_coverage` limpio (no recorded issue) sobre `paper_runner.py`, `regime_confirmation.py`, `paper_certification.py`, `test_memory_repository.py`, CLI.

## Riesgos
- El despliegue requiere **reconstruir la imagen** (R1.1); hasta entonces el server no tiene la confirmación de regímenes.
- La evidencia de regímenes aún no se valida en vivo (depende del período de 7 días).
- Estrategia `baseline-v1` puede producir trades escasos (esperado).

## Deuda técnica
- Imagen desplegada desactualizada vs. rama (se resuelve en R1.1).
- G8 (persistencia DB reducida, 8 tablas) se mantiene intencionalmente para R2.
- La credencial rotada quedará sin sanear en la historia pasada (histórico `ef08869`); saneo aplicado hacia adelante.

## Commit propuesto
```
feat(phase-16): confirmación de regímenes + gate certificación + fixtures pgvector + saneado S1
```

## Autorización solicitada
¿Autorizas el commit de los archivos listados (tracked + nuevos) en la rama `feature/paper-regime-certification` con el mensaje propuesto?

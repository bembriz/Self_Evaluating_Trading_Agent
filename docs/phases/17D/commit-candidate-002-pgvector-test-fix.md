# Commit Candidate Report — pre-17E maintenance (pgvector test debt)

> NO staging / NO commit / NO push ejecutados. Solo preparación.
> Deuda PREEXISTENTE confirmada en base limpia 96998e6 (no regresión 17D).

## Objetivo

Alinear los fixtures del test de integración de memoria con la dimensión
pgvector del schema (384). Test-only: 1 archivo tocado, cero código productivo.

## Rama / Base

| Campo | Valor |
|---|---|
| branch | feature/phase-08-llm-decision-agent (pre-existente) |
| base commit | dd3f803 |

## Archivos

- **Modificados:** `tests/integration/test_memory_repository.py` (+16/−4:
  helper determinista `embedding_384(first, second)`, labels de espacio `|384`).
- **Creados:** este archivo.
- Producción (`src/`, migraciones, config embeddings): intacta.

## Tests ejecutados

| Suite | Resultado |
|---|---|
| `tests/integration/test_memory_repository.py -v` | 3 passed |
| `tests/integration` | 15 passed |
| Global `--cov=src --cov-branch --cov-fail-under=90` | 624 passed, 1 skipped · **95.52%** ✔ |
| `ruff check src tests` / `ruff format --check src tests` / `mypy src tests` (214) | PASS / PASS / PASS |

Semántica preservada: vectores idénticos → similitud 1.0 (filtro temporal
anti-leakage intacto); espacios distintos siguen aislados. Sin random.

## Seguridad / Safety

- PRODUCTION_CODE_CHANGED=NO · PROTECTED_RUNTIME_DIFF=CLEAN
- HOLDOUT_STATE=PRISTINE · sin acceso a FINAL_HOLDOUT
- Sin secretos en el diff.

## Riesgos / Deuda

Riesgo mínimo (solo tests). La deuda queda saldada; no se crea deuda nueva.

## Mensaje de commit propuesto

```
test(integration): align memory embeddings with pgvector dimension
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

# Commit Candidate Report — {{FECHA}}

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

> Qué problema resuelve este commit.

## Rama

| Campo | Valor |
|---|---|
| branch | |
| base commit | |

## Archivos

- **Creados:**
- **Modificados:**
- **Eliminados:**

## Diff

```bash
# pegar git diff --stat y enlace/ruta al diff completo
```

## Arquitectura afectada

> Módulos y contratos tocados; blast radius (codebase-memory-mcp si está disponible).

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| | | |

## Cobertura

> Número exacto.

## Calidad

```bash
uv run ruff check .        # resultado:
uv run ruff format --check .
uv run mypy src tests      # resultado:
uv run pytest              # resultado:
```

## Seguridad

- [ ] Sin secretos en el diff
- [ ] Sin archivos .env ni credenciales
- [ ] Secret scanning (si aplica) limpio

## Riesgos

>

## Deuda técnica

>

## Mensaje de commit propuesto

```
type(scope): descripción corta

- detalle 1
- detalle 2
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

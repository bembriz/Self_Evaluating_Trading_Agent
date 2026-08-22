# Dependency Proposal — DP-001 · Dependencias de desarrollo del arnés

> Obligatoria ANTES de instalar cualquier paquete, herramienta, imagen o servicio (PRD §11).
> Flujo: DISCOVER → PLAN/DRY-RUN → REPORT (este documento) → **USER GATE** → APPLY → VALIDATE → EVIDENCE.
**Fecha:** 2026-08-22 · **Fase:** 00 (Arnés) · **Estado:** PENDING USER GATE

## Propuesta

| # | Paquete | Versión | Tipo | Uso |
|---|---|---|---|---|
| 1 | pyyaml | ≥6.0 | runtime del arnés | Parseo de `harness/state/progress.yaml` |
| 2 | pytest | ≥8.3 | dev | Suite de tests de los scripts del arnés |
| 3 | pytest-cov | ≥5.0 | dev | Cobertura objetivo ≥80% (gate_check/coverage) |
| 4 | ruff | ≥0.8 | dev | Lint/format de los scripts del arnés |
| 5 | markdown | ≥3.7 | dev (grupo PDF) | MD→HTML para gen_pdf.py |
| 6 | weasyprint | ≥63 | dev (grupo PDF) | HTML→PDF reportes de fase (PRD §75) |

Comando de instalación (solo tras APPROVED):

```bash
cd harness && uv sync && uv add --dev markdown weasyprint
```

## Problema que resuelve

Los scripts `progress/gate_check/gen_report/new_phase` requieren PyYAML para operar; sin pytest no hay validación verificable del arnés (requisito #9 del usuario); sin markdown+weasyprint no existe conversión MD→PDF exigida por PRD §75.

## Por qué es necesario

Bloquea: VALIDATE de G2 (tests), el flujo completo de gates (coverage gate) y el cierre de cualquier fase (reporte PDF).

## Alternativas consideradas

| Alternativa | Por qué se descarta |
|---|---|
| Ledger en JSON sin dependencias | Rechazado en diseño aprobado: YAML es más legible/mantenible como ledger humano-auditable |
| Pandoc para PDF | Instalación binaria de sistema mayor y global; WeasyPrint queda aislado en venv del proyecto |
| Sin tests del arnés | Viola requisito #9 (calidad separada de implementación) |

## Razón para NO implementarlo internamente

Parser YAML correcto (anclas, multi-línea, tipos) y motor HTML→PDF son infraestructura estándar; reimplementarlos viola el principio de mínima complejidad del PRD §85.

## Impacto en arquitectura

Ninguno sobre el producto. Aislado en `harness/pyproject.toml` + `harness/.venv` (gitignored). El producto (Fase 01+) tendrá su propio pyproject raíz.

## Seguridad

- pyyaml: uso exclusivo con `yaml.safe_load` (nunca load).
- pytest/pytest-cov/ruff: herramientas dev estándar MIT/BSD.
- markdown: MIT. weasyprint: BSD-3.
- Todas con repositorios activos y adopción masiva. Resolución fijada en `uv.lock`.

## Impacto en licencia del proyecto

Sin conflicto (MIT/BSD compatibles).

## Rollback

```bash
rm -rf harness/.venv harness/uv.lock   # elimina todo rastro; cero impacto fuera de harness/
```

## DRY-RUN ejecutado (pre-gate)

```text
$ uv lock                                    # solo resolución, SIN crear .venv ni instalar
Resolved 11 packages in 677ms                # pyyaml+pytest+cov+ruff resueltos OK
$ ldconfig -p | grep pango                   # libs sistema para weasyprint
libpangoft2-1.0.so.0 / libpangocairo-1.0.so.0 / libpangomm-2.48.so.1 → PRESENTES ✔
```

Nota: `uv add --dry-run` no existe en uv 0.11.25; se usó resolución vía lock + verificación de libs del sistema.

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED (6 paquetes) ☐ APPROVED parcial (indicar cuáles) ☐ REJECTED
Fecha/comentario:

---
name: reporting-fases
description: Usar cuando una fase complete su scope y haya que generar el reporte de fase (30 secciones PRD §76), convertirlo a PDF, o preparar el paquete de cierre para el USER GATE
---

# reporting-fases — Reportes de fase MD+PDF

## Propósito

Producir el reporte ejecutivo por fase (`docs/phases/phase-XX-report.md`, 30 secciones PRD §76) con datos objetivos prellenados desde el ledger, y su PDF al solicitar cierre (PRD §75).

## Cuándo usar

- Al completar scope de fase (después de `gate_check` sin FAIL).
- Cuando el usuario pida cierre/gate de fase.
- Para regenerar el reporte tras cambios (con `--force`).

**Cuándo NO usar:** reportes intermedios informales; documentación de producto (usa documentation-standards).

## Entradas → Salidas

- **Entradas:** ledger actualizado, evidencias en `docs/phases/<XX>/evidence/`, checklist UAT.
- **Salidas:** `phase-XX-report.md` (+`.pdf`) con las 30 secciones completas.

## Checklist

1. Confirma `gate_check.py --phase XX` sin FAIL (los MANUAL pueden estar pendientes).
2. `python3 harness/scripts/gen_report.py --phase XX` → esqueleto con datos verificados.
3. Completa secciones cualitativas (resumen, riesgos, deuda, rollback, competencias §80).
4. Pega resultados EXACTOS de tests/cobertura desde los logs de evidencia.
5. Genera PDF: `uv run --project harness python harness/scripts/gen_pdf.py docs/phases/phase-XX-report.md`.
6. Presenta reporte + checklist UAT al usuario para decisión del gate.

## Estructura obligatoria (30)

Executive Summary · Objetivo · Scope · Out of Scope · Arquitectura antes/después · Archivos creados/modificados · Dependencias · Configuración · Comandos exactos · Rutas · API endpoints · Migraciones · Tests · Coverage · E2E · UAT · Evidencias · Métricas · Logs · Git diff · Riesgos · Seguridad · Deuda técnica · Known Issues · Rollback · Competencias · DoD · Estado CI · Solicitud de aprobación.

La sección 27 (competencias) alimenta el componente educativo: qué se practicó y dónde (PRD §80).

## Errores comunes

- Comandos "teóricos" en §10: solo comandos realmente ejecutados (verificados en evidencia).
- Cobertura redondeada "a mano": usa el número de coverage.json.
- Enviar a gate con secciones vacías: rechazo directo.

## Referencias

- Plantilla viva: `harness/templates/reporte-fase.md`.
- Globales: documentation-standards, superpowers:verification-before-completion.

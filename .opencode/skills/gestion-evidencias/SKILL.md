---
name: gestion-evidencias
description: Usar cuando se ejecute cualquier comando cuya resultado deba quedar auditable para un gate, cuando se registre cobertura/lint/tests como evidencia, o antes de declarar PASS de cualquier verificación
---

# gestion-evidencias — Evidencia verificable o no ocurrió

## Propósito

Toda afirmación de estado (tests PASS, lint verde, dataset congelado, gate listo) debe respaldarse con evidencia registrada, fechada y reproducible. **Sin evidencia no hay % en el ledger ni gate.**

## Cuándo usar

- Tras ejecutar suites de tests, linters, type checks, builds.
- Al generar artefactos verificables (coverage.json, manifests, checksums, PDFs).
- Antes de `progress.py mark-done` (exige ruta de evidencia) y antes de gates.

**Cuándo NO usar:** exploración informal, lecturas, borradores desechables.

## Entradas → Salidas

- **Entradas:** comando a documentar + fase actual.
- **Salidas:** `docs/phases/<XX>/evidence/<nombre>.log` (salida completa + exit code) y entrada en `evidence/log.md`.

## Checklist

1. Identifica la fase activa (`docs/phases/<XX>/`).
2. Envuelve el comando: `bash harness/scripts/evidence.sh <fase> <nombre> -- <comando...>`.
3. Verifica que `exit=` del log coincide con lo que reportas.
4. Para cobertura: añade `--cov-report=json:docs/phases/<XX>/evidence/coverage.json` (gate_check lo lee).
5. En el reporte de fase, referencia SIEMPRE rutas relativas al repo.

## Reglas duras

- Prohibido editar logs de evidencia a posteriori; si algo falló, queda registrado y se corrige en nueva corrida.
- Un log sin `exit=0` NO es evidencia de PASS (puede ser evidencia de hallazgo).
- Los tests del propio arnés cuentan: su suite vive en `harness/tests/`.

## Comandos compuestos

Registra cada comando por separado (`ruff check`, luego `ruff format --check`): así cada exit code es auditable de forma independiente. Si necesitas una secuencia como un solo artefacto, envuélvela explícitamente: `evidence.sh <fase> <nombre> -- bash -c 'cmd1 && cmd2'`.

## Errores comunes

- Pegar salidas parciales "bonitas" en el reporte sin log subyacente.
- Registrar evidencia de otra fase (mezcla trazabilidad).
- Declarar PASS verbal sin wrapper (gate_check no lo verá).

## Referencias

- Plantillas y flujo: AGENTS.md §8–10. Globales: superpowers:verification-before-completion.

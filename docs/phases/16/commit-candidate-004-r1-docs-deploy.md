# Commit Candidate Report — R1 docs + deploy evidence

- **Fecha:** 2026-09-02
- **Rama:** `feature/paper-regime-certification`
- **Base:** `40fe28e` `fix(phase-16): reconexión WS en paper-runner sin reset de estado + RegimeClassifier con deque`

## Objetivo
Versionar la auditoría solicitada contra PRD §3.1, los dos planes de remediación y la evidencia del despliegue R1 aplicado en `lenovosrv`.

## Archivos
- `docs/audits/2026-09-02-auditoria-lenosrv-vs-prd-3-1.md`
- `docs/phases/16/remediation-01-sin-llm-7-dias.md`
- `docs/phases/16/remediation-02-llm-7-dias.md`
- `docs/phases/16/commit-candidate-003-r1.md`
- `docs/phases/16/commit-candidate-004-r1-docs-deploy.md`
- `docs/phases/16/evidence/deploy-r1-lenosrv.log`
- `docs/phases/16/evidence/log.md`

## Diff
Cambio documental y evidencia. No modifica código productivo, tests, configuración local ni infraestructura versionada.

## Arquitectura afectada
Ninguna. Documenta el estado desplegado y los planes de remediación.

## Tests / Calidad
- Última verificación fresca de código (R1.2, previa a este commit documental): `444 passed, 1 skipped`.
- `ruff check .` y `mypy src tests` limpios en R1.2.
- Para este diff documental: `git diff --check` sin errores.

## Seguridad
- Scan del diff pendiente: sin `1712@Lenovo`, sin `DEEPSEEK_API_KEY` con valor y sin `BYBIT_API_SECRET` con valor.
- La auditoría documenta S1 sin reproducir el secreto.

## Riesgos
- Bajo: solo documentos y evidencia.
- Los documentos del repo canónico se copiaron al worktree correcto para versionarlos en `feature/paper-regime-certification`.

## Commit propuesto
```text
docs(phase-16): auditoría lenovosrv y planes R1/R2
```

## Autorización solicitada
¿Autorizas este commit documental/evidencia en la rama `feature/paper-regime-certification`?

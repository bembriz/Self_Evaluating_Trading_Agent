# UAT — Fase 00: Governance & Agent Bootstrap (Arnés)

> Prueba de aceptación de usuario (HITL). El agente NO puede aprobar UAT (PRD §74).
> Ejecuta los pasos tal cual desde la raíz del repo y completa "Resultado observado" y el veredicto final.

## Precondiciones

| # | Precondición | Verificada ☐ |
|---|---|---|
| 1 | Estar en la raíz del repo (`cd ~/Documentos/proyectos/Self-Evaluating_Trading_Agent`) | ☐ |

## Entradas / Datos

Ninguna externa. Solo comandos locales.

## Pasos

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | `python3 harness/scripts/progress.py report` | Tabla con 19 fases; Fase 00 = 12/12 done, 100%; global ≈5.26%; ETA en rango; "Bloqueos: ninguno" |
| 2 | `python3 harness/scripts/gate_check.py --phase 00` | 5 PASS · 0 FAIL · 2 MANUAL (uat-approved, user-approval); exit=0 |
| 3 | `ls .opencode/skills/ \| wc -l` | 22 directorios de skills |
| 4 | Abrir `docs/skill-gap/SKILL_GAP.md` | Matriz real: 11 globales reutilizadas + 22 a crear, sin duplicados |
| 5 | Abrir `AGENTS.md` §3–7 | Ciclo por fase, routing a skills, reglas críticas, flujo git/infra claros |
| 6 | Abrir `opencode.json` | `git commit/push/merge/tag`, `uv add`, `pip install`, `docker compose up/down` → `"ask"`; `rm -rf /`, `curl * \| sh` → `"deny"`; `.env` protegido en read/edit |
| 7 | Abrir `docs/phases/phase-00-report.md` (+`.pdf`) | 30 secciones completas, cobertura exacta 92.74%, comandos reales §10 |
| 8 | `uv run --project harness pytest harness/tests -q` | ~54 passed, 0 failed |
| 9 | Abrir `docs/phases/00/DP-001-harness-dev-dependencies.md` | DECISIÓN DEL USUARIO: APPROVED (ya aplicada) |
| 10 | Abrir `docs/phases/00/DP-002-codebase-memory-mcp.md` | Proposal completa PENDIENTE de tu decisión |
| 11 | Intentar en otra sesión OpenCode un `git commit` o `uv add X` | El agente queda bloqueado esperando TU aprobación (enforcement) |

## Evidencia a adjuntar

Salidas de pasos 1–2 y 8 (captura o copia), y nota del comportamiento observado en el paso 11 si se prueba.

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
| 11 | | | |

## Incidencias encontradas

> Desviaciones, errores o comportamientos inesperados.

---

## VEREDICTO UAT: APPROVED
<!-- Sustituir PENDING por APPROVED o REJECTED. gate_check exige el veredicto APPROVED visible (los comentarios HTML no cuentan) al check uat-approved -->
Decisor: Usuario (aprobación explícita en sesión)  Fecha: 2026-08-22
Comentario: "aprobada" — registrada por el agente en nombre del usuario conforme a su instrucción directa.
Comentario:

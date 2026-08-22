# Reporte de Fase 00 — Governance & Agent Bootstrap (Arnés)

**Fecha:** 2026-08-22
**Estado de fase:** gate_requested (pendiente UAT + aprobación humana)
**Avance fase:** 100% · **Avance global:** 5.26% (cap 90% aplicado hasta APPROVED)
**Gate:** requested

---

## 1. Executive Summary

Se construyó el arnés agéntico completo que gobernará el desarrollo del Self-Evaluating Trading Agent: orquestador (`AGENTS.md`), 22 skills especializadas versionadas, enforcement técnico vía `opencode.json` (instalaciones y git-write requieren aprobación humana), scripts verificadores con tests (cobertura 92.74%), ledger objetivo de progreso (19 fases · 151 entregables mapeados del PRD §79) y plantillas de gobierno. Dos Dependency Proposals quedaron documentadas (DP-001 aprobada e instalada; DP-002 pendiente de decisión). El arnés quedó validado end-to-end: progreso objetivo, checklist de gate honesto y evidencia auditable funcionando sobre el estado real.

## 2. Objetivo

Crear las reglas, herramientas y controles bajo los que OpenCode desarrollará el proyecto por fases (PRD §79 Fase 00), sin adelantar funcionalidad del producto.

## 3. Scope

- Orquestación separada de capacidades (AGENTS.md + skills).
- Enforcement doble: instrucciones + permission rules.
- Progreso/ETA objetivos sobre ledger versionado.
- Testing del propio arnés (unit, cobertura ≥80%).
- Skill Gap Report real con catálogo aprobado en G1.
- Flujos: gate de fase, infraestructura (DISCOVER→…→EVIDENCE), commits con autorización.
- Integración propuesta de codebase-memory-mcp (gated).
- Componente educativo por fase.

## 4. Out of Scope

Cualquier componente funcional del trading agent (market data, features, LLM runtime, risk engine, dashboard…): pertenecen a Fases 01–18. Instalación real de codebase-memory-mcp (gated en DP-002). Repo remoto/CI ejecutante (el usuario crea GitHub; workflows llegan en Fase 01).

## 5. Arquitectura antes/después

**Antes:** repositorio vacío salvo `docs/PRD`. Sin gobernanza, sin skills, sin verificación objetiva.
**Después:** tres planos — (1) `AGENTS.md` orquestador; (2) catálogo `.opencode/skills/` (22 nuevas + 21 globales reutilizadas); (3) `harness/` scripts+ledger+plantillas con enforcement en `opencode.json`. Ver árbol completo en `docs/design/harness-design.md` §3.

## 6. Archivos creados

~55 archivos: AGENTS.md, opencode.json, README.md, .gitignore, .env.example, harness/{pyproject.toml, uv.lock, scripts×7, state/progress.yaml, templates×5, tests×7}, docs/design/harness-design.md, docs/skill-gap/SKILL_GAP.md, docs/adr/ADR-0001-harness.md, docs/phases/00/* (DP-001, DP-002, evidence×7), .opencode/skills/**22 SKILL.md**, este reporte.

## 7. Archivos modificados

`harness/scripts/gate_check.py`, `ledger.py`, `gen_report.py`, `gen_pdf.py`, `new_phase.py`, `evidence.sh` (correcciones derivadas de los propios tests); `progress.yaml` (solo vía scripts).

## 8. Dependencias

DP-001 **APPROVED e instalada**: pyyaml, pytest, pytest-cov, ruff, markdown, weasyprint (dev, aisladas en `harness/.venv`). DP-002 **PENDING**: codebase-memory-mcp.

## 9. Configuración

`.gitignore` (secretos, datasets/, artefactos), `.env.example` sin credenciales, `opencode.json` (permission rules), `meta.reglas` del ledger (cap 90%, coverage mínima por fase: 00→80%).

## 10. Comandos exactos (verificados)

```bash
git init -b main
cd harness && uv sync && uv add --dev markdown weasyprint   # tras DP-001 APPROVED
uv run --project harness pytest harness/tests --cov=harness/scripts --cov-branch \
  --cov-report=json:docs/phases/00/evidence/coverage.json -q        # exit=0 · 92.74%
uv run --project harness ruff check harness/scripts harness/tests   # exit=0
python3 harness/scripts/progress.py report                          # % objetivo + ETA
python3 harness/scripts/gate_check.py --phase 00                    # 5 PASS·0 FAIL·2 MANUAL
python3 harness/scripts/gen_report.py --phase 00 --force            # este reporte
```

## 11. Rutas

Ver §6. Evidencia: `docs/phases/00/evidence/log.md`.

## 12. API endpoints

N/A (sin producto aún).

## 13. Migraciones

N/A.

## 14. Tests

| Nivel | Ejecutado | Resultado | Evidencia |
|---|---|---|---|
| Unit (scripts arnés) | ☑ 54 casos | PASS | evidence/unit-tests-arnes.log |
| Integration | ☐ N/A fase 00 | — | — |
| E2E (flujo arnés sandbox) | ☑ manual demostrado | OK | §10 + historial de sesión |

## 15. Coverage

**92.74%** global branch (objetivo 80%) — gate_check PASS. Por script: gate_check 97%, progress 97%, gen_report 96%, new_phase 96%, ledger 90%, gen_pdf 85%.

## 16. E2E

Demo sandbox real: mark-done→report (%+ETA)→gate_check (detectó FAILs correctos antes de G3; hoy solo MANUALs)→gen_report→(PDF abajo). El validador independiente (subagente) ejercitó retrieval/application de las 22 skills: 8 escenarios respondidos correctamente; 3 hallazgos corregidos.

## 17. UAT

- Checklist: `docs/uat/phase-00-uat.md`
- Veredicto: PENDIENTE (lo ejecuta y decide el usuario)

## 18. Evidencias

Índice: `docs/phases/00/evidence/log.md` — lint, lint-format, typing, unit-tests (×4 corridas, incluye fallos iniciales honestos), coverage.json.

## 19. Métricas

151 entregables definidos · 12/12 Fase 00 done · 22 skills (~310 palabras media) · 54 tests · 92.74% cov · 0 secretos · ETA global inicial: 13–23 días (velocidad observada).

## 20. Logs relevantes

Primera corrida de tests registró 14 fallos → 5 bugs reales corregidos (shift de evidence.sh, find_repo_root, mkdir destino, subparsers CLI, asserts). Historial íntegro en evidence/unit-tests-arnes.log (corridas sucesivas).

## 21. Git diff

Primer commit candidate del repo (todo es nuevo). Diff disponible a solicitud; se generará al preparar el Commit Candidate Report.

## 22. Riesgos

- Skills dependen de disciplina del modelo: mitigado por enforcement técnico + scripts verificadores.
- Ledger desincronizado si se edita a mano: regla dura + validador de esquema (`require_valid`).
- WeasyPrint requiere libs pango (presentes ✔, verificadas en DP-001).
- ~~codebase-memory-mcp pendiente~~ RESUELTO en cierre: DP-002 APPROVED, instalado v0.10.8, repo indexado (944 nodos · 1,632 aristas), smoke queries OK.

## 23. Seguridad

`.env` denegado lectura/edición en opencode.json y excluido de Git; sin secretos en el repo (verificación manual + reglas); installs gated; comandos destructivos deny. Pendiente: secret scanning automático llega con CI (Fase 01).

## 24. Deuda técnica

1. Validación completa de skills tipo "pressure scenarios" con subagentes (hecho: retrieval/application sobre muestra representativa + mecánica total).
2. CI no ejecutable hasta remoto GitHub.
3. mypy del arnés diferido a Fase 01 junto al typing del producto.
4. Instalación codebase-memory-mcp pendiente decisión DP-002.

## 25. Known Issues

`uv add --dry-run` inexistente en uv 0.11.25 (documentado en infra-control y DP-001). Doble convención de rutas en docs/phases (phase-XX-report.md plano + XX/evidence/) asumida y documentada.

## 26. Rollback

Eliminar directorios creados (harness/, .opencode/, docs/{design,skill-gap,uat,adr,phases/00}) y archivos raíz añadidos; revertir commit una vez exista. Sin impacto externo (nada instalado fuera de harness/.venv; rollback DP-001 = borrar .venv+lock).

## 27. Competencias de Ingeniería de Software practicadas (PRD §80)

Git (init/trunk-based policy/approvals) · Agentic Development (skills, orchestration, enforcement) · Engineering Governance (gates, DoD, evidencia) · Testing Automation (suite+cobertura+TDD aplicado a scripts) · Documentation as Code (30 secciones, plantillas) · Developer Experience · Security basics (secrets, permissions) · Product thinking (DoD por fase, métricas).

## 28. Definition of Done

scope complete ☑ · tests PASS ☑ · integration N/A ☑ · E2E flujo ☑ · UAT approved ☐ (usuario) · coverage ≥80% ☑ · CI green ☐ N/A sin remoto · lint ☑ typing ☑ · documentation ☑ · evidence ☑ · diff reviewed ☐ (en Commit Candidate) · user approved ☐

## 29. Estado CI

Sin remoto todavía: usuario creará repo GitHub; pipelines desde Fase 01. Verificación local equivalente ejecutada (§10).

## 30. Solicitud de aprobación

- [x] Presentado al usuario (junto con instructivo UAT `docs/uat/phase-00-uat.md` y DP-002 pendiente)
- **DECISIÓN DEL USUARIO:** ☐ APPROVED ☐ REJECTED
- Comentario:

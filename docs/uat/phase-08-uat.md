# UAT — Fase 08: LLM Decision Agent

> Prueba de aceptación de usuario (HITL). El agente NO puede aprobar UAT.
> Ejecuta los pasos tal cual y completa "Resultado observado" y el veredicto final.

## Precondiciones

| # | Precondición | Verificada ☐ |
|---|---|---|
| 1 | Repo en rama `feature/phase-08-llm-decision-agent` con los cambios de la fase en working tree | ☐ |
| 2 | `uv` instalado y `.venv` sincronizado (`uv sync`) | ☐ |
| 3 | (Opcional, para el Paso 5) `DEEPSEEK_API_KEY` definida en `.env` — sin ella, el fail-safe debe actuar igualmente | ☐ |

## Entradas / Datos

No se requieren datos externos. Los tests usan `httpx.MockTransport` y fakes; jamás consultan el LLM real (salvo el Paso 5 opcional).

## Pasos

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | `uv run pytest tests --ignore=tests/integration --cov=src --cov-branch --cov-fail-under=90` | `240 passed`; `Total coverage: 93.85%` (≥90%) |
| 2 | `uv run pytest tests/test_deepseek.py tests/test_decision_agent.py -v` | Todos PASS: JSON inválido→HOLD, schema inválido (confidence 9.9)→HOLD, HTTP 500→HOLD, timeout→HOLD, presupuesto agotado→HOLD **sin llamar** al proveedor |
| 3 | `python3 harness/scripts/gate_check.py --phase 08` | `5 PASS · 0 FAIL · 2 MANUAL` (los MANUAL son UAT y aprobación, este documento) |
| 4 | `uv run python -c "from infrastructure.llm.prompts import FilePromptStore; p=FilePromptStore().load('decision','v001'); print(p.version, p.hash[:12])"` | `v001` + hash hex de 64 chars (prompt versionado inmutable, PRD §37) |
| 5 | (Opcional, con API key real) Ejecutar una decisión contra DeepSeek real con un MarketState mínimo | Si la API responde válido: decisión BUY/SELL/HOLD estructurada; si falla cualquier cosa: HOLD con `fallback_reason` — nunca excepción ni texto libre |
| 6 | Revisar `docs/phases/08/evidence/log.md` y `docs/phases/phase-08-report.md` | Evidencias completas y coherentes con lo observado |

## Evidencia a adjuntar

Salida de los comandos de los Pasos 1–4 (y 5 si se ejecuta), pegada en "Resultado observado" o adjunta como log.

## Resultado observado

| Paso | Resultado observado | ¿Coincide? (SÍ/NO) | Notas |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |
| 6 | | | |

## Incidencias encontradas

> Nota conocida (no bloqueante): los 11 tests de integración requieren PostgreSQL vía Docker (puerto 5433), no disponible en este entorno. No guardan relación con el código de esta fase.

---

## VEREDICTO UAT: APPROVED
<!-- Sustituir PENDING por APPROVED o REJECTED. gate_check exige el veredicto APPROVED visible (los comentarios HTML no cuentan) al check uat-approved -->
Decisor: usuario (sesión opencode)  Fecha: 2026-08-23
Comentario: Aprobado por el usuario tras presentación del reporte de fase y evidencias.

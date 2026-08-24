# Reporte de Fase 08 — LLM Decision Agent

**Fecha:** 2026-08-23
**Estado de fase:** in_progress (pendiente UAT + gate)
**Avance fase:** 100.0% entregables con evidencia · **Gate mecánico:** 5 PASS · 0 FAIL · 2 MANUAL
**Rama:** `feature/phase-08-llm-decision-agent` (sin commits: pendiente autorización, flujo-commits)

---

## 1. Executive Summary

Se implementó el LLM Decision Agent completo con dominio puro independiente del proveedor (PRD §17–20, §37–39, §60): contrato `LLMProvider`/`PromptStore` como Protocols, adapter DeepSeek con retries limitados y fail-safe HOLD total, salida estructurada validada estrictamente con Pydantic v2, presupuestos experiment/mensual con alertas 50/75/90% y bloqueo a 100%, prompts versionados inmutables (`prompts/decision/v001.md`) y metadatos de reproducibilidad §38–39. El LLM no especifica cantidades ni toca riesgo. Suite unitaria 240 PASS, cobertura 93.85% (≥90%), ruff/format/mypy estrictos limpios.

## 2. Objetivo

Dotar al agente de un decisor LLM con contrato de salida estructurada (PRD §19), fail-safe HOLD ante cualquier condición de error (PRD §20), coste medido y presupuestado (PRD §60), y versionado de prompts/experimentos para reproducibilidad (PRD §37–39) — PRD §79 Fase 08.

## 3. Scope

- `LLMProvider` + `PromptStore` (Protocols `@runtime_checkable`) y `DecisionResult` en `application/ports/llm.py`.
- Dominio puro: `TradingDecision`, `DecisionContext`, `TradingMemory` (mínima), `Budget`/`BudgetState`/`BudgetLevel`, `compute_cost`, `LLMCallRecord`, `Prompt`.
- Adapter `DeepSeekProvider` (httpx, MockTransport en tests): retries 429/5xx con backoff, HOLD ante timeout/HTTP/JSON/schema/choices vacíos.
- Servicios de aplicación: `CostMonitor` (registro tokens/costo por llamada + budgets) y `DecisionAgent` (fail-safe HOLD).
- Schemas Pydantic: `DecisionResponse` (Literal BUY/SELL/HOLD, confidence [0,1], intensity LOW/MEDIUM/HIGH) y `DeepSeekChatResponse`.
- Prompts versionados: `prompts/decision/v001.md` + `FilePromptStore`.
- Extensión `ExperimentMetadata` con campos §39 (prompt_version, llm_provider/model, embedding_*, risk_config_version) incluidos en el `experiment_id`.
- Configuración: settings LLM (modelo `deepseek-v4-flash`, precios USD/Mtok, budgets) en `settings.py` + `config/base.yaml`.

## 4. Out of Scope

- Persistencia de `llm_calls`/`llm_costs` en PostgreSQL (tablas §55 → fase de observabilidad; hoy el registro es en memoria vía `CostMonitor`).
- OpenAI/Ollama adapters (PRD §18: posteriores).
- Embeddings/RAG y filtrado temporal de memoria (fase 09): `TradingMemory` es mínima para el contrato.
- Integración del DecisionAgent en workers/API (llega con fases 10–11).

## 5. Arquitectura antes/después

Antes: capas domain/application/infrastructure sin módulo LLM (`infrastructure/llm/` vacío).
Después: puerto en `application/ports/llm.py`; dominio puro en `domain/llm/*` + `domain/trading/decision.py`; adaptadores en `infrastructure/llm/{deepseek,prompts,schemas}.py`; orquestación en `application/services/{decision_agent,cost_monitor}.py`. Dependencias apuntan hacia dentro (infrastructure → application/domain); el dominio no conoce httpx ni pydantic.

## 6. Archivos creados

`src/application/ports/llm.py`, `src/application/services/cost_monitor.py`, `src/application/services/decision_agent.py`, `src/domain/llm/{__init__,budget,call,cost,prompt}.py`, `src/domain/memory/memory.py`, `src/domain/trading/decision.py`, `src/infrastructure/llm/{deepseek,prompts,schemas}.py`, `prompts/decision/v001.md`, tests: `test_decision.py`, `test_llm_ports.py`, `test_llm_budget.py`, `test_llm_cost.py`, `test_llm_prompt.py`, `test_llm_schemas.py`, `test_prompt_store.py`, `test_deepseek.py`, `test_decision_agent.py`.

## 7. Archivos modificados

`src/domain/experiments/experiment.py` (campos §39), `src/settings.py`, `config/base.yaml`, `.env.example`, `tests/test_experiment.py`, `tests/test_settings.py`.

## 8. Dependencias

Ninguna nueva. Se reutilizaron `httpx` y `pydantic-settings` ya aprobados en fases anteriores. Sin Dependency Proposal requerida.

## 9. Configuración

Nuevas claves en `config/base.yaml`/`Settings`: `llm_provider=deepseek`, `llm_model=deepseek-v4-flash`, `llm_base_url`, `llm_api_key` (SecretStr, vacío), `llm_timeout=30.0`, `llm_temperature=0.0`, `llm_price_input_mtok=0.27`, `llm_price_output_mtok=1.10`, `llm_experiment_budget_usd=5.0`, `llm_monthly_budget_usd=50.0`, `prompts_dir=prompts`. `.env.example` documenta `DEEPSEEK_API_KEY` y presupuestos. Sin secretos versionados.

## 10. Comandos exactos

Registrados en `docs/phases/08/evidence/log.md`:

```bash
uv run pytest tests --ignore=tests/integration --cov=src --cov-branch --cov-fail-under=90   # 240 passed, 93.85%
uv run ruff check .                                                                          # All checks passed
uv run ruff format --check .                                                                 # 158 files formatted
uv run mypy src tests                                                                        # Success: no issues (136 files)
```

## 11. Rutas

Sin rutas nuevas (API no tocada en esta fase).

## 12. API endpoints

Ninguno añadido ni modificado.

## 13. Migraciones

Ninguna (sin cambios de esquema en esta fase).

## 14. Tests

| Nivel | Ejecutado | Resultado | Evidencia |
|---|---|---|---|
| Unit | ✅ 240 passed | PASS (93.85% cobertura branch ≥90%) | `docs/phases/08/evidence/tests-unit.log` |
| Integration | ⚠️ 11 errors — PostgreSQL (puerto 5433/compose) no disponible: Docker ausente en este entorno. Sin relación con el código de la fase (no toca BD). | N/A entorno | `docs/phases/08/evidence/integracion-db-no-disponible.log` |
| E2E | ☐ | Pendiente (requiere fases 10–11: risk→paper→outcome) | — |

## 15. Coverage

93.85% global branch (umbral 90%). TOTAL: 2308 statements, 133 missed, 358 branches, 23 partial. Log completo en evidencia `tests-unit.log`. Los nuevos módulos de la fase están cubiertos por sus suites específicas (dominio, schemas, adapter con MockTransport, servicios con fakes).

## 16. E2E

No aplica aún: el flujo completo market→features→decision→risk→paper→outcome llega en fases 10–11. Verificado smoke end-to-end del wiring disponible: `FilePromptStore` carga `v001` real → `render_decision_messages` produce 2 mensajes deterministas → presupuesto operativo.

## 17. UAT

- Checklist: `docs/uat/phase-08-uat.md`
- Veredicto: PENDIENTE

## 18. Evidencias

Índice en `docs/phases/08/evidence/log.md`: `tests-unit`, `lint`, `format-check`, `mypy`/`typing`, `integracion-db-no-disponible`.

## 19. Métricas

9/9 entregables completados. Fail-safes cubiertos: 8 condiciones PRD §20 (timeout/network_error, http_error, invalid_json ×2 niveles, invalid_schema, empty_choices, budget_exhausted, prompt_not_found, provider_error:*). Retries: 429/5xx hasta `max_retries=2` con backoff exponencial.

## 20. Logs relevantes

Smoke test de wiring: prompt `v001` cargado (hash SHA-256 válido), 2 mensajes renderizados, presupuesto no bloqueado. Salidas completas en los logs de evidencia.

## 21. Git diff

Rama `feature/phase-08-llm-decision-agent` desde `5918312` (main). Cambios en working tree/staging SIN commit (pendiente autorización). Diff completo a generar para el Commit Candidate Report (flujo-commits).

## 22. Riesgos

- Alias de modelo (`deepseek-v4-flash`) puede cambiar detrás del proveedor → mitigado con registro `reported_model_version` por llamada (§38).
- Precios USD/Mtok configurables pueden desactualizarse → presupuestos y alertas limitan el impacto; revisar antes de experimentos largos.
- Límites float en umbrales de presupuesto con límites arbitrarios (deferred minor) → sin efecto con la configuración actual.

## 23. Seguridad

API key como `SecretStr` desde `.env` (nunca versionado); `.env.example` sin valores. El LLM no puede especificar montos (prompt + contrato Pydantic sin campos monetarios) ni toca Risk Engine. Tests nunca consultan el LLM real (MockTransport/fakes).

## 24. Deuda técnica

- Persistencia `llm_calls`/`llm_costs` en BD (hoy memoria) → fase observabilidad.
- `CostMonitor._calls` acumulado sin lector todavía (para observabilidad).
- Validación de config (p. ej. `max_retries` negativo) pendiente de capa de validación de settings.

## 25. Known Issues

- Tests de integración requieren Docker/PostgreSQL no disponible en este entorno (preexistente).
- Minors diferidos registrados en ledger SDD: umbral float en `Budget.level()`, guard path-traversal en `FilePromptStore`, test que no asserta cost==0 en provider-error.

## 26. Rollback

Rama dedicada sin merge: descartar con `git checkout main && git branch -D feature/phase-08-llm-decision-agent` (tras autorización). Ningún cambio de esquema ni de infraestructura que revertir.

## 27. Competencias de Ingeniería de Software practicadas

LLM Integration (contrato estructurado + proveedor), Ports & Adapters (Protocol runtime_checkable, adapter HTTP), Structured AI Outputs (Pydantic estricto + fail-safe), Cost Engineering (precios/Mtok, budgets con alertas y bloqueo), Testing (TDD RED→GREEN por tarea, mocks de red), Arquitectura hexagonal (dependencias toward-domain).

## 28. Definition of Done

- [x] Scope completo (9/9 entregables)
- [x] Unit tests PASS (240)
- [ ] Integration PASS (bloqueo de entorno: Docker ausente; código no afectado)
- [ ] E2E PASS (pertenece a fases 10–11)
- [ ] UAT approved (PENDIENTE — usuario)
- [x] Cobertura ≥90% (93.85%)
- [x] Lint green / typing green
- [x] Evidencias completas
- [ ] Diff reviewed + user approval (gate)

## 29. Estado CI

Pipeline remoto no ejecutado en esta sesión (sin push — requiere autorización). Verificaciones locales equivalentes: lint/format/mypy/coverage green.

## 30. Solicitud de aprobación

- [ ] Presentado al usuario
- **DECISIÓN DEL USUARIO:** ☐ APPROVED ☐ REJECTED
- Comentario:

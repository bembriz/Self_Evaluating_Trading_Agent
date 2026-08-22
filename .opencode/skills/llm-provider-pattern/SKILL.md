---
name: llm-provider-pattern
description: Usar al implementar o modificar el contrato LLMProvider, adapters (DeepSeek/OpenAI/Ollama), salida estructurada del Decision Agent, fail-safe HOLD, versionado de prompts y presupuesto de coste (PRD §17-20, §37-38, §60)
---

# llm-provider-pattern — LLM como decisor supervisado

## Propósito

Dominio independiente del proveedor; contrato estricto de salida estructurada; fail-safe total hacia HOLD; coste medido y presupuestado. **El LLM no especifica cantidades ni toca riesgo.**

## Cuándo usar

- Implementar `LLMProvider` (Protocol) y adapters DeepSeek/OpenAI/Ollama.
- Validar respuestas contra el esquema PRD §19 (decision/confidence/intensity/factors).
- Versionar prompts (`prompts/<tipo>/v###.md`) y registrar reproducibilidad (§38).
- Gestionar budgets experiment/mensual con alertas 50/75/90 y bloqueo a 100%.

**Cuándo NO:** decisiones de riesgo/sizing (risk-engine); embeddings/RAG (rag-memoria).

## Contrato de decisión (PRD §19)

```json
{"decision": "BUY|SELL|HOLD", "confidence": 0..1, "intensity": "LOW|MEDIUM|HIGH",
 "rationale_summary": "...", "supporting_factors": [...], "risk_factors": [...]}
```

Fail-safe (PRD §20): timeout/API caída/presupuesto agotado/JSON inválido/schema inválido/confidence fuera de rango/respuesta incompleta/modelo no disponible ⇒ **HOLD**. Nunca reutilizar la última decisión ni interpretar creativamente.

## Reproducibilidad por llamada (persistir SIEMPRE)

provider · requested_model · reported_model_version · request/response · prompt_hash · market_state_hash · temperature/params · timestamp · latency · tokens in/out · cost.

Experimentos cerrados: cachear decisiones para replay sin re-consultar.

## Checklist de adapter nuevo

1. Protocol implementado sin filtrar tipos del SDK al dominio.
2. Timeouts + retries limitados + budget check ANTES de llamar.
3. Parseo estricto → Pydantic → inválido ⇒ HoldDecision(reason registrada) + métrica `llm_failures`.
4. Registro completo §38 en `llm_calls`/`llm_costs`.
5. Fake provider para tests (testing-integration); LLM real jamás en CI.
6. Cambio de prompt/modelo = nueva versión + nuevo experimento (nunca silencioso).

## Errores comunes

- Confiar en JSON mode sin validar schema igualmente.
- Temperature/params sin registrar.
- Prompt editado in-place rompiendo trazabilidad.

## Referencias

- PRD §17–20, §37–39, §60. Skills: testing-integration, risk-engine, gestion-evidencias.

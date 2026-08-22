---
name: arquitectura-hexagonal
description: Usar al decidir estructura de módulos, crear puertos/adaptadores, documentar ADRs, refactorizar capas, o cuando surja la duda de dónde vive una pieza de código en src/ (PRD §8-9)
---

# arquitectura-hexagonal — Monolito modular pragmático

## Propósito

Hexagonal / Ports & Adapters SIN capas sin responsabilidad real. El dominio es puro y testeable; la infraestructura es reemplazable; las interfaces son finitas.

## Cuándo usar

- Ubicar código nuevo en `src/{domain,application,infrastructure,interfaces}`.
- Definir un puerto (Protocol) y sus adaptadores (Bybit, LLM, embeddings, DB).
- Documentar decisiones relevantes como ADR (PRD §82).
- Refactors que cruzan límites de capa (analizar blast radius antes).

**Cuándo NO:** decisiones triviales sin impacto arquitectónico (no crear ADR por gusto).

## Mapa de dependencias (regla dura)

```text
domain  ←  application  ←  interfaces
              ↑
        infrastructure (implementa puertos definidos en application/domain)
```

- `domain/`: entidades puras, reglas (risk, portfolio). CERO I/O, cero frameworks.
- `application/services|commands|queries`: orquestación; define PUERTOS (Protocols).
- `infrastructure/bybit|database|llm|embeddings|execution|observability`: adaptadores concretos.
- `interfaces/api|web|cli`: entrada del usuario; delgada siempre.
- Prohibido: domain importando infrastructure; lógica de negocio en adapters/routers.

## Checklist — puerto nuevo

1. ¿Dos implementaciones plausibles o necesidad de fake para tests? Si no, quizá no hace falta puerto aún (mínima complejidad).
2. Protocol tipado en application/ports.
3. Adaptador en infrastructure + fake para tests.
4. Inyección explícita desde main/composition root.
5. ADR si la elección es relevante.

## Errores comunes

- Sobre-abstracción: puerto con una sola implementación eterna.
- Anémico+transaccional mezclado: entidades con invariantes (p.ej. SELL solo reduce posición).
- Import circular entre capas = señal de diseño roto.

## Referencias

- PRD §8–9, §85 (mínima intervención), §82 (ADRs). Skills: fastapi-standards, llm-provider-pattern, codebase-memory-mcp (impact analysis pre-refactor).

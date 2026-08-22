# ADR-0001 — Arnés agéntico modular con enforcement técnico y ledger objetivo

**Fecha:** 2026-08-22
**Estado:** accepted

## Contexto

El PRD exige desarrollo por fases con aprobación humana, testing exhaustivo (≥90% cobertura), control total de dependencias/infraestructura, Git con autorización obligatoria y progreso objetivo (no subjetivo). El agente ejecutor (OpenCode) necesita reglas operativas separadas de las capacidades por dominio. Alternativas: monolito documental en AGENTS.md (sin validación objetiva), o MCP de gobierno propio (complejidad prohibida por PRD §85).

## Decisión

Construir un **arnés modular** en tres planos: (1) `AGENTS.md` como orquestador delgado; (2) catálogo de 22 skills especializadas versionadas en `.opencode/skills/` reutilizando 21 globales donde aplica (Skill Gap Report); (3) scripts verificadores Python + ledger YAML (`harness/state/progress.yaml`) como única fuente del % de avance, con mutación exclusiva vía scripts y evidencia obligatoria. Enforcement dual: instrucciones + `opencode.json` permission rules (`ask` para git-write e instalaciones, `deny` para destructivos). Gates internos G1/G2/G3 durante la construcción del propio arnés.

## Alternativas consideradas

| Opción | Consecuencia si se elige |
|---|---|
| Todo en AGENTS.md | % subjetivo, gates sin verificación, archivo ilegible a las 3 fases |
| MCP custom de gobierno | Dependencia nueva + desarrollo considerable; viola mínima complejidad |

## Consecuencias

### Positivas

- % y ETA calculados sobre evidencia verificada, nunca estimación del agente.
- Separación real implementar≠probar≠validar≠aprobar.
- Catálogo auditable y portable (todo en Git).

### Negativas / trade-offs aceptados

- ~40 archivos iniciales que mantener sincronizados con el PRD.
- Fricción deliberada en cada instalación/commit (es el objetivo).
- Cobertura pragmática (~80%) para scripts del arnés, distinta del estándar del producto (90%).

### Neutras

- WeasyPrint/markdown como dev-deps solo para PDF de cierre (DP-001).

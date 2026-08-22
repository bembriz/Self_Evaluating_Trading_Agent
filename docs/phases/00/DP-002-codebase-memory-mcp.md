# Dependency Proposal — DP-002 · codebase-memory-mcp (PRD §12)

> Flujo: DISCOVER → PLAN/DRY-RUN → REPORT (este documento) → **USER GATE** → APPLY → VALIDATE → EVIDENCE.
**Fecha:** 2026-08-22 · **Fase:** 00 · **Estado:** PENDING USER GATE

## Propuesta

| Campo | Valor |
|---|---|
| Nombre | codebase-memory-mcp ([github.com/DeusData/codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp)) |
| Versión propuesta | latest release estable (pin SHA-256 de `checksums.txt` en el momento de APPLY) |
| Tipo | ☐ paquete Python ☐ CLI ☐ imagen Docker ☐ servicio ☒ extensión/MCP |
| Comando de instalación | Descarga manual del tarball linux-amd64 + `./install.sh` incluido (**sin** pipe a bash de red); el instalador detecta OpenCode y registra el MCP |

## Problema que resuelve

PRD §12 exige memoria estructural del codebase (Index→Understand→Impact Analysis→Implement→Re-index→Verify) y blast radius pre-commit. Sin él, cada refactor depende de greps costosos y propensos a omisiones.

## Por qué es necesario

Bloquea: análisis de impacto fiable, detección de duplicados, call graphs, conservación de decisiones (ADRs integrados), y el checklist obligatorio de blast radius de `flujo-commits`.

## Alternativas consideradas

| Alternativa | Por qué se descarta |
|---|---|
| Solo grep/glob + lectura | Escala mal; alto consumo de tokens; sin call graph ni impact mapping |
| Otros servidores MCP de índice | Menor cobertura de lenguajes/sin grafo persistente/servicios externos |
| No instalar | Viola requisito explícito del PRD §12 y del usuario (#7) |

## Razón para NO implementarlo internamente

Parser multi-lenguaje (tree-sitter ×158), grafo persistente SQLite, Hybrid LSP y servidor MCP son años de ingeniería; existe solución MIT madura, auditada (SLSA 3, OpenSSF Scorecard, VirusTotal publicado por release).

## Impacto en arquitectura

Ninguno en runtime del producto. Opera como herramienta del agente: binario nativo + config MCP de OpenCode + `.codebase-memory/graph.db.zst` opcional en repo (decidiremos gitignore vs commit en APPLY).

## Seguridad

- Licencia **MIT**. Procesamiento **100% local**, sin telemetría ni API keys.
- Distribución firmada con checksums publicados; política de release auditable (SECURITY.md).
- Lee el codebase y escribe solo en configs de agentes locales y caché propia.
- Rollback: `codebase-memory-mcp uninstall` (elimina entradas propias; índices tras confirmación).

## Impacto en licencia del proyecto

Sin conflicto (MIT).

## Rollback

1. `codebase-memory-mcp uninstall`
2. Verificar ausencia de entradas en config de OpenCode
3. Opcional: borrar `~/.cache/codebase-memory-mcp/`

## DRY-RUN ejecutado (pre-gate)

- README oficial revisado (2026-08-22): requisitos, instalación manual soportada, 15 tools, detección automática de OpenCode confirmada.
- Sin descargas ni ejecuciones aún: instalación real ocurre solo tras APPROVED.

---

**DECISIÓN DEL USUARIO:** ☒ APPROVED
Fecha/comentario: 2026-08-22 — aprobado en sesión junto al gate de Fase 00.

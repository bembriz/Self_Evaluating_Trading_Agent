---
name: codebase-memory-mcp
description: Usar antes de modificar arquitectura o componentes existentes, al iniciar cada fase (Index→Understand→Impact), antes de commits para blast radius, o al buscar dependencias/call graphs/duplicados en el codebase (PRD §12)
---

# codebase-memory-mcp — Memoria estructural del desarrollo

## Propósito

Grafo de conocimiento persistente del propio repositorio (15 tools MCP): entender módulos, localizar dependencias, impact analysis, evitar duplicados y medir blast radius antes de tocar código. **Distinta** de la Trading Memory del producto.

## Cuándo usar

- Inicio de fase: Index → Understand → Impact Analysis → Implement → Re-index → Verify.
- Antes de refactor o cambios cruzando módulos.
- Pre-commit: `detect_changes` mapea diff→símbolos afectados con clasificación de riesgo (alimenta Commit Candidate Report).
- Buscar implementaciones existentes antes de crear algo nuevo.

## Estado e instalación

- **INSTALADO**: v0.10.8 (`~/.local/bin/codebase-memory-mcp`) tras DP-002 APPROVED (2026-08-22).
- Registrado en `~/.config/opencode/opencode.jsonc` + agentes read-only (scout/verify/auditor) + skill global.
- CLI directo: `codebase-memory-mcp cli <tool> --flag valor` (útil fuera del agente).
- Si el índice queda obsoleto tras muchos cambios: re-ejecutar `index_repository --repo-path .`.

## Flujo obligatorio por fase

```text
1. index_repository      (o verificar índice vigente / watcher activo)
2. get_architecture      (lenguajes, capas, entry points, hotspots)
3. search_graph/semantic_query  (entender lo que vas a tocar)
4. trace_path            (callers/callees del símbolo objetivo)
5. IMPLEMENTAR
6. re-index + detect_changes   (diff→símbolos)
7. blast radius en commit-candidate.md antes de pedir autorización
```

## Tools principales

| Tool | Uso |
|---|---|
| `index_repository` | Indexa/actualiza el grafo |
| `get_architecture` | Vista general: paquetes, rutas, hotspots |
| `search_graph` | Búsqueda estructural por nombre/tipo/file |
| `semantic_query` | Búsqueda semántica ("cómo se calcula el sizing") |
| `trace_path` | Call graph entrante/saliente |
| `detect_changes` | Diff sin commit → símbolos afectados + riesgo |
| `check_index_coverage` | Valida cobertura del índice sobre rutas citadas |
| Cypher-like queries | `MATCH (f:Function)-[:CALLS]->(g) WHERE f.name='x' RETURN g.name` |
| `manage_adr` | ADRs persistidos entre sesiones |

## Checklist pre-commit (blast radius)

1. Índice actualizado (post-cambios).
2. `detect_changes` sobre el working tree.
3. Símbolos afectados clasificados por riesgo; los HIGH se enumeran en el reporte de commit.
4. `check_index_coverage` limpio sobre archivos tocados.
5. Conclusión explícita: "el cambio toca N módulos, M callers externos" — sin esta frase no se solicita commit.

## Errores comunes

- Consultar un índice obsoleto tras editar mucho código (re-indexar primero).
- Confiar en una única búsqueda semántica para afirmaciones negativas ("nadie usa esto"): verificar con search_graph + grep.
- Mezclar la memoria del desarrollo con la Trading Memory del producto (conceptos distintos).

## Referencias

- PRD §12. Repo: DeusData/codebase-memory-mcp. Skills: flujo-commits, arquitectura-hexagonal.

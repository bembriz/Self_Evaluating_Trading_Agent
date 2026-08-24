# Dependency Proposal — DP-003: Stack de embeddings locales + cliente pgvector (Fase 09)

> Obligatoria ANTES de instalar cualquier paquete, herramienta, imagen o servicio (PRD §11).
> Flujo: DISCOVER → PLAN/DRY-RUN → REPORT (este documento) → USER GATE → APPLY → VALIDATE → EVIDENCE.

## Propuesta

| Campo | Valor |
|---|---|
| Nombre | `pgvector` (cliente Python) + `fastembed` (embeddings locales ONNX) |
| Versión propuesta | `pgvector>=0.5.0` · `fastembed>=0.4` (última estable resuelta por uv) |
| Tipo | ☒ paquetes Python (producción, grupo base) |
| Comando de instalación | `uv add pgvector fastembed` |

## Problema que resuelve

Fase 09 (PRD §79): Trading Memory con PostgreSQL+pgvector — tabla `memory_items` con columna `vector`, índice de similitud coseno, recuperación top-k y filtrado temporal. Falta: (a) el tipo `Vector`/operadores de distancia para SQLAlchemy, (b) un runtime de embeddings local para el `EmbeddingProvider` con modelo recomendado `intfloat/multilingual-e5-small` (PRD §33).

## Por qué es necesario

Sin `pgvector` (Python) no hay forma tipada de mapear la columna `vector` en SQLAlchemy 2.x ni de ejecutar `<=>` (distancia coseno) desde el ORM. Sin un runtime de embeddings no existe el `EmbeddingProvider` local exigido por PRD §33 ("Implementación inicial: local"). "No hacer nada" deja 6 de los 8 entregables de la fase bloqueados.

## Alternativas consideradas

| Alternativa | Por qué se descarta |
|---|---|
| SQL crudo para vector (sin paquete pgvector) | Pérdida de tipado/seguridad del ORM; duplicación manual de operadores; mantenimiento mayor que el paquete |
| `sentence-transformers` (torch) | ~2 GB+ de dependencias (torch/triton/cuda); desproporcionado para e5-small en CPU |
| API remota de embeddings (OpenAI) | PRD §33 exige implementación inicial LOCAL; añade coste por token y dependencia de red |
| Implementación interna (ONNX a mano) | Reinventa tokenización/pooling cuantización ya resueltos; alto riesgo de error silencioso en calidad de embeddings |

## Razón para NO implementarlo internamente

La serialización de vectores y el cómputo de similitud son protocolo de Postgres (`pgvector`), y la inferencia ONNX con tokenizador correcto es lógica de dominio ajena al proyecto: reimplementarla introduce riesgo de embeddings incorrectos sin beneficio didáctico adicional.

## Impacto en arquitectura

- `pgvector`: solo `infrastructure/database` (tipos de columna + índice HNSW en migraciones). El dominio sigue puro.
- `fastembed`: solo detrás del puerto `EmbeddingProvider` (adapter en `infrastructure/embeddings/`). Dominio y aplicación no lo importan.
- Sin cambios en interfaces/API.

## Seguridad

- `pgvector` 0.5.0: BSD-3-Clause? No — licencia **MIT**? (verificada en APPLY: `pgvector-python` es MIT/postgres-like; se registra licencia exacta en la evidencia). Mantenido por ankane/pgvector (ecosistema oficial de la extensión). Superficie mínima (sin binarios propios).
- `fastembed`: **Apache-2.0**, mantenido por Qdrant. Descarga modelos ONNX desde HuggingFace Hub en primer uso (supply-chain: modelo fijado por nombre+dimensión en config; sin ejecución remota de código arbitrario más allá del runtime ONNX).
- Ambos en el índice de PyPI oficiales; sin post-install scripts.

## Impacto en licencia del proyecto

Proyecto privado de investigación; ambas licencias permisivas (MIT/Apache-2.0) compatibles. Sin obligación de revelar código propio.

## Rollback

`uv remove pgvector fastembed` + revertir migración Alembic correspondiente (`downgrade`). Los modelos ONNX cacheados (~100–300 MB en `~/.cache`) se borran a mano si se desea.

## DRY-RUN ejecutado (pre-gate)

```bash
$ uv pip install --dry-run pgvector
 + pgvector==0.5.0                      # 1 paquete

$ uv pip install --dry-run fastembed
 # 14 paquetes: onnxruntime, tokenizers, huggingface-hub, protobuf, py-rust-stemmers, tqdm...
 # SIN torch (frente a sentence-transformers, que arrastra torch/triton)

$ uv pip install --dry-run sentence-transformers   # descartado por peso
 + triton==3.7.1 ... (decenas de paquetes, GBs)
```

Nota de entorno: Docker no está disponible en esta sesión, por lo que los tests de integración contra PostgreSQL+pgvector (puerto 5433) quedan registrados como pendientes de entorno, igual que en Fase 08.

---

**DECISIÓN DEL USUARIO:** ☒ APPROVED ☐ REJECTED — Fecha: 2026-08-23 Comentario: Aprobado en sesión; embeddings locales vía fastembed

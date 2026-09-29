# Commit Candidate Report — 2026-09-29

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> **Candidate 016 — M9-B: cierre documental del Full DEVELOPMENT review (solo docs/evidencia).**

## Objetivo

Registrar el cierre documental de M9-B: la comparación **OLD (close-only) vs NEW
(trade-sequence)** sobre los 647 días de `DEVELOPMENT`, sus métricas económicas, exit
reasons y la revisión de consistencia de los artefactos. **Sin código, sin tests.**

**NO** ejecuta replay (los artefactos ya existían). **NO** toca WF/HOLDOUT,
`paper/certification`, `progress.yaml` ni `src/**`.

## Rama

| Campo | Valor |
|---|---|
| branch | `medalion` |
| base commit | `fcba380e423ee717fe6ffd1244f14ffb072c40b2` (HEAD == BASE esperado) |

## Archivos

- **Creados (16):**
  - `docs/phases/23/m9b-full-development.md` (Full DEVELOPMENT OLD vs NEW)
  - `docs/phases/23/m9b-review.md` (revisión de consistencia + conclusión M9-B)
  - `docs/phases/23/commit-candidate-016.md` (este reporte)
  - `docs/phases/23/evidence/m9b-full-*.log` (**9**: `01-run`, `02-metrics`, `03-verify`
    + 6 per-combination)
  - `docs/phases/23/evidence/m9b-review-consistency.log`
  - `docs/phases/23/evidence/m9b-cand016-{quality,secret-scan,staged-final}.log`
- **Modificados (1):** `docs/phases/23/evidence/log.md` (índice)
- **Eliminados:** ninguno
- **Total staged (previsto):** 17
- **Código/tests:** **0** · **`progress.yaml`:** **0** · **`src/domain/risk/`:** 0 ·
  **deployment / paper / certification / safeguard:** 0

## Diff

```bash
$ git diff --cached --stat        # snapshot antes de este reporte (13 archivos)
 docs/phases/23/evidence/log.md          |   8 +
 docs/phases/23/evidence/m9b-full-*.log  |  ... (9 logs)
 docs/phases/23/evidence/m9b-review-consistency.log | ...
 docs/phases/23/m9b-full-development.md  | ...
 docs/phases/23/m9b-review.md            | ...
 13 files changed, 561 insertions(+)

$ git diff --cached --numstat | grep -E '(src|tests|harness)/' || echo CODE_DIFF=0
CODE_DIFF=0
```

## Arquitectura afectada

- **Ninguna** en `src/**` ni en tests. Solo documentación de fase y evidencia.
- Artefactos analizados (remotos, en lenovosrv): `/srv/fast/medallion/m9b-full/`
  (6 `summary.json` + 6 `trades.jsonl`), generados por el runner ya commiteado en
  `fcba380` (candidate 015).
- **Blast radius:** código sin cambios ⇒ impacto estructural 0.

## Índice del grafo

- [ ] Índice re-indexado tras el commit (`index_repository`) → *pendiente de APPROVED*
- [x] Sin cambios de código ⇒ no requiere reindexación estructural; docs/evidencia no
  aportan símbolos al grafo.

## Validaciones

| Requisito | Resultado | Evidencia |
|---|---|---|
| `M9B_FULL_DEVELOPMENT=PASS` | **PASS** | `m9b-full-development.md`, `m9b-full-01-run.log` |
| `M9B_REVIEW=PASS` | **PASS** | `m9b-review.md`, `m9b-review-consistency.log` |
| `REPLAY_RERUN_REQUIRED=NO` | **NO** | `m9b-review.md` §6 |
| `ARTIFACTS_CONSISTENT=YES` | **YES** (6+6, 0 discrepancias) | `m9b-review-consistency.log` |
| parity PASS ×3 | **PASS** (baseline/donchian/bollinger) | `m9b-full-02-metrics.log` |
| `LEGACY_M7_LEDGER_IDENTICAL=YES` | **YES** (`6d64b62b…`) | `m9b-full-03-verify.log` |
| `WF_READS=0` / `HOLDOUT_READS=0` | **0 / 0** | `m9b-full-03-verify.log` |
| paper/certification intactos | **NO cambiados** | `m9b-full-03-verify.log` |
| `PROGRESS_YAML_CHANGED` | **NO** | diff staged |
| quality PASS | **PASS** | `m9b-cand016-quality.log` |
| secret scan PASS | **PASS** | `m9b-cand016-secret-scan.log` |

### Exit reasons (semántica mantenida)

`TP=take_profit` · `SL=stop_loss` · `trailing_stop` = categoría independiente ·
`llm_sell` (OLD raw) → presentación `strategy_exit` (raw preservado) ·
secundaria permitida `protective_exits = stop_loss + trailing_stop`.

| Estrategia | Modelo | TP | SL | trailing | strategy_exit (pres.) | net_pnl |
|---|---|---|---|---|---|---|
| baseline | OLD | 155 | 322 | 62 | 92 | −22.812989 |
| baseline | NEW | 131 | 362 | 78 | 60 | −24.864136 |
| donchian | OLD | 199 | 325 | 36 | 279 | −27.741589 |
| donchian | NEW | 215 | 556 | 95 | 121 | −38.777176 |
| bollinger | OLD | 2 | 115 | 0 | 274 | −16.936591 |
| bollinger | NEW | 4 | 155 | 0 | 246 | −18.183960 |

### Alcance explícito

`DEVELOPMENT_ONLY=YES` · `OOS_CONCLUSION=NO` · `POPULATIONS_DIRECTLY_COMPARABLE=NO` ·
Phase 21R = `REFERENCE_ONLY_DIFFERENT_BOUNDARY_WINDOW=YES`.

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Calidad (ruff + format + mypy, 290 archivos) | **PASS** | `m9b-cand016-quality.log` |
| Consistencia de artefactos (recompute de 6+6) | **PASS** | `m9b-review-consistency.log` |
| Full DEVELOPMENT (ya ejecutado, no repetido) | **PASS** (6/6 rc=0) | `m9b-full-01-run.log` |

## Cobertura

No aplica (commit documental; sin cambios de código/tests). Cobertura del producto sin
cambios respecto de `fcba380` (global 90.56%, medallion 94.27%).

## Calidad

```bash
uv run ruff check .                 # All checks passed!
uv run ruff format --check .        # 333 files already formatted
uv run mypy src tests               # Success: no issues found in 290 source files
```

## Seguridad

- [x] 6 patrones HITS=0 (clave privada, `AKIA…`, credenciales, `Bearer`, URL `user:pass@`,
  archivos sensibles) — `m9b-cand016-secret-scan.log`
- [x] Sin `.env`/`.pem`/`.key`/`id_rsa`/`.p12` staged
- [x] Hex-64 fuera de logs: **2 identificadores de artefacto públicos** documentados
  (`dataset_id` `gold-replay-5ca68f44…` y `manifest sha256` `c095d574…`) en
  `m9b-full-development.md`; **no** son credenciales. Código/tests: 0.

## Riesgos

- Commit exclusivamente documental: no altera comportamiento ni datos.
- Los resultados son **in-sample / DEVELOPMENT**: no deben citarse como rentabilidad futura
  ni viabilidad OOS (`OOS_CONCLUSION=NO`).
- La comparación OLD/NEW **no es directamente comparable** (`POPULATIONS_DIRECTLY_COMPARABLE=NO`).

## Deuda técnica

- No se repitió una corrida completa de 647 días para un contraste de determinismo a esa
  escala (sí smoke 3 días); no es bloqueante y no obliga a repetir (`REPLAY_RERUN_REQUIRED=NO`).
- Los ledgers viven en `/srv/fast/medallion/m9b-full/` (caché NVMe reproducible); solo los
  summaries extraídos y los logs quedan en el repo.

## Mensaje de commit propuesto

```
docs(medallion): record M9-B full development review

- m9b-full-development.md: OLD (close-only) vs NEW (trade-sequence) sobre los 647 dias
  DEVELOPMENT (62112 velas); 6 combinaciones, metricas economicas, exit reasons y paridad
- m9b-review.md: revision de consistencia de 6 summaries + 6 ledgers (0 discrepancias) y
  conclusion tecnica M9-B
- exit reasons: TP=take_profit, SL=stop_loss, trailing_stop independiente,
  llm_sell -> strategy_exit (presentacion, raw preservado); protective_exits=SL+trailing
- DEVELOPMENT_ONLY=YES, OOS_CONCLUSION=NO, POPULATIONS_DIRECTLY_COMPARABLE=NO;
  Phase21R REFERENCE_ONLY_DIFFERENT_BOUNDARY_WINDOW
- evidencia: m9b-full-*.log + m9b-review-consistency.log; legacy M7 intacto (6d64b62b...);
  WF/holdout=0; paper/certification intactos
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

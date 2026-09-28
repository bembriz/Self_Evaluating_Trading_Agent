# Commit Candidate Report — 2026-09-27

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

Registrar M3 (Idempotent Bybit Bronze Historical Trade Ingestion): downloader Bronze
stdlib-only con manifiesto determinista, split guard DEVELOPMENT fail-closed, CLI para
lenovosrv, 30 unit tests sin red, UAT RUN1/RUN2 + negative en el servidor y la marca
`23/m3-bronze` = done en el ledger.

## Rama

| Campo | Valor |
|---|---|
| branch | `medalion` |
| base commit | `69607b4d2c8a0ebf0e2b771949dbd94c05795ed2` (= `origin/medalion`) |

## Archivos

- **Creados (23):**
  - `src/infrastructure/medallion/split_guard.py` — `ensure_development_day()` fail-closed, ventana `[2023-09-09..2025-06-16]` alineada a `splits/v1.json`
  - `src/infrastructure/medallion/bronze.py` — descarga idempotente (`.part` → gzip magic/CRC → SHA-256 → manifest atómico → `os.replace`), `HashConflictError` fail-closed, base URL restringida a `https://public.bybit.com/spot` (prohíbe `/trading/`), marker `LENOVO_DATA`, ops en `ops-downloads.jsonl` separado del manifest
  - `src/infrastructure/medallion/cli.py` — CLI argparse (`--dest-dir --symbol --dates --base-url --require-marker`), exit 0/1/2
  - `src/infrastructure/medallion/__init__.py` — export de la capa
  - `tests/test_bronze_ingest.py` — 30 unit tests sin red
  - `docs/phases/23/m3-bronze-ingestion.md` — doc de milestone
  - `docs/phases/23/evidence/m3-*` — 17 evidencias (incluye intentos fallidos documentados: m3-02, 02b–02d, 05, y el precommit `m3-10`)
  - `docs/phases/23/commit-candidate-005.md` — este fichero
- **Modificados (2):** `docs/phases/23/evidence/log.md` (+31 líneas), `harness/state/progress.yaml` (`23/m3-bronze` → `done` vía `progress.py mark-done`)
- **Eliminados:** ninguno

## Diff

```bash
$ git diff --cached --stat
26 files changed, 1480 insertions(+), 3 deletions(-)
$ git diff --cached --check
rc=0   # 0 hallazgos
```

## Arquitectura afectada

- Nuevo módulo `infrastructure.medallion` (capa Bronze del pipeline Medallion, skill
  `medallion-market-data` + ADR-0005/0007). Sin cambios en `domain/`, API, DB ni
  runners; zero dependencias nuevas (solo stdlib: `urllib`, `gzip`, `hashlib`, `json`).
- lenovosrv (fuera de git): UAT dejó 3 archivos Bronze + manifest + ops log en
  `/srv/data/medallion/bronze/bybit/spot/ETHUSDT/` (HDD con marker verificado);
  contenedores productivos intactos (IDs/StartedAt = baseline M2).
- Blast radius: consumidores futuros = Silver (M4); por ahora solo la CLI.

## Índice del grafo

- [ ] Índice re-indexado tras el commit (`index_repository`) — pendiente post-commit
- [ ] Cobertura verificada sobre archivos tocados (`check_index_coverage`) — pendiente
      post-commit (`docs/`, `harness/state` parcialmente excluidos por diseño)

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| `pytest tests/test_bronze_ingest.py` (30 tests) | PASS | `m3-01-unit-tests.log`, `m3-02e-lint-quality.log` |
| `pytest tests --ignore=tests/integration` | PASS — 985 passed, 1 skipped | `m3-08b-product-unit-tests-with-count.log` |
| `ruff check .` + `ruff format --check .` + `mypy src tests` | PASS (0 hallazgos, 273 files) | `m3-09-repo-quality.log` |
| Precommit verify (ruff+format+mypy+30 tests) | PASS | `m3-10-precommit-verify.log` |
| UAT RUN1 lenovosrv (3 días) | PASS — `downloaded=3`, hash canónico `f5dd2cc8…` | `m3-05b-uat-run1.log` |
| UAT RUN2 idempotencia | PASS — `downloaded=0 skipped=3`, hashes/manifest idénticos | `m3-06-uat-run2-idempotent.log` |
| UAT negative (WF/pre-DEV/holdout/trading/marker) | PASS — exit correctos, sin particiones nuevas | `m3-07-uat-negative.log` |

## Cobertura

- Módulos nuevos: **93.94%** (bronze 95%, cli 90%, split_guard 91%, `__init__` 100%)
  con `--cov=infrastructure.medallion --cov-branch --cov-fail-under=90` → PASS.
- Suite completa del producto: 985 passed / 1 skipped (PG local caído = preexistente).

## Calidad

```bash
uv run ruff check .                 # All checks passed!
uv run ruff format --check .        # 314 files already formatted
uv run mypy src tests               # Success: no issues found in 273 source files
uv run pytest tests --ignore=tests/integration
                                    # 985 passed, 1 skipped
```

## Seguridad

- [x] Sin secretos en el diff (grep de `password|api_key|secret|token|BEGIN … PRIVATE`: solo la variable argparse `token` y el test de traversal `../etc/passwd`)
- [x] Sin archivos `.env` ni credenciales; evidencia m3 sin `$SUDO_PASS` (preflight/UTA sin sudo)
- [x] Preexistente y NO de este commit: credencial sudo histórica ya versionada en logs de
  fase 16 → "Credencial sudo histórica detectada en evidencia ya versionada. Rotación
  requerida y limpieza de historial pendiente en gate separado."
  (`SECURITY_CREDENTIAL_ROTATION_REQUIRED=YES`, `GIT_HISTORY_CLEANUP_REQUIRED=YES`)

## Riesgos

- Bajo: código nuevo aislado (`infrastructure/medallion`) sin consumidores activos aún.
- El split guard usa ventana por día completo; días de borde (17-06-2025, 08-09-2023)
  quedan excluidos por diseño (coincide con el criterio de M3).
- UAT descargó 3 días (~14 MB) — sin bulk; el manifest operativo del servidor difiere
  del repo (esperado: los datos viven en lenovosrv, no en git).

## Deuda técnica

- `coverage.json` global de repo no re-ejecutado en M3 (umbral del gate de fase al cierre).
- Validación de contenido (columnas Silver) → M4.
- Rotación de credencial + limpieza de historial → gate separado (preexistente).

## Mensaje de commit propuesto

```
feat(medallion): M3 idempotent Bronze Bybit Spot ingestion

- infrastructure/medallion: downloader .part -> gzip CRC -> sha256 -> manifest
  deterministico -> rename atomico; hash mismatch FAIL CLOSED; base URL solo
  public.bybit.com/spot (prohibido /trading/); marker LENOVO_DATA
- split_guard: ventana DEVELOPMENT [2023-09-09..2025-06-16] fail-closed pre-red
- CLI stdlib para lenovosrv (sin dependencias nuevas): exit 0/1/2
- tests: 30 unit tests sin red; cobertura modulos 93.94%
- UAT lenovosrv: RUN1 downloaded=3 -> RUN2 skipped=3, hashes/manifest identicos;
  WF/holdout/pre-DEV rechazados sin crear particiones
- ledger: 23/m3-bronze -> done (via progress.py mark-done)
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

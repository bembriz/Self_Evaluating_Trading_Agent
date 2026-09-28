# M3 — Idempotent Bybit Bronze Historical Trade Ingestion

**Fecha:** 2026-09-27 (UTC-6) / 2026-09-28 (UTC en lenovosrv)
**Rama:** `medalion` @ `69607b4d2c8a0ebf0e2b771949dbd94c05795ed2` (precondición verificada)
**Alcance:** downloader Bronze idempotente de trades Spot de Bybit + UAT de 3 días consecutivos en lenovosrv.
**Gate:** instrucción directa del usuario (M3). Restricciones: NO commit, NO push, NO bulk download.

## Ejecución (evidencia en `docs/phases/23/evidence/`)

| Paso | Artefacto | Resultado |
|---|---|---|
| 00 schema sample | `m3-00-schema-sample.log` | PASS — schema real `id,timestamp,price,volume,side`; 402 115 líneas/día; `ETHUSDT_2024-06-01.csv.gz` 2 995 239 B sha256 `f5dd2cc8a8f5…` |
| 01 unit tests | `m3-01-unit-tests.log` | PASS — 30 tests; cobertura módulo 93.94% (bronze 95%, cli 90%, split_guard 91%) |
| 02 ruff | `m3-02-ruff.log` | exit=1 — 4 issues (orden de imports, E501); corregido en 02b–02e |
| 02b–02d lint | `m3-02b/c/d*.log` | exit=1 — cada reintento exponía el siguiente fallo (format, `CaptureFixture[str]`, E501) |
| 02e lint-quality | `m3-02e-lint-quality.log` | **PASS** — `ruff check` + `ruff format --check` + `mypy --strict` (5 files) + 30 tests + cobertura ≥90% |
| 03 preflight lenovosrv | `m3-03-preflight.log` | PASS — Python 3.12.3; marker `LENOVO_DATA` ✓; destino escribible; 870 G libres; baseline de contenedores intacta |
| 04 deploy copy | `m3-04-deploy-copy.log` | PASS — `tar|ssh` → `/tmp/m3/src`; `IMPORT_OK`; CLI `--help` OK (stdlib puro, sin venv) |
| 05 UAT RUN1 | `m3-05-uat-run1.log` | exit=1 — error operativo: script ejecutado localmente en vez de vía `ssh bash -s` (corregido en 05b) |
| 05b UAT RUN1 | `m3-05b-uat-run1.log` | **PASS** — `downloaded=3`; hash de `2024-06-01` = `f5dd2cc8a8f5…` (idéntico a la muestra canónica) |
| 06 UAT RUN2 | `m3-06-uat-run2-idempotent.log` | **PASS** — `downloaded=0 skipped=3`; hashes y manifest byte-idénticos; gzip CRC OK, 402 115 líneas |
| 07 UAT negative | `m3-07-uat-negative.log` | **PASS** — WF/holdout/pre-DEV → exit 1 sin crear particiones; fecha mala → 2; base `/trading/` y marker ausente → 1 |
| 08 unit suite repo | `m3-08-product-unit-tests.log` | exit=0 |
| 08b unit suite (conteo) | `m3-08b-product-unit-tests-with-count.log` | **PASS — 985 passed, 1 skipped** (`--ignore=tests/integration`, PG local caído = preexistente) |
| 09 repo quality | `m3-09-repo-quality.log` | **PASS** — `ruff check .` (314 files) + `ruff format --check .` + `mypy src tests` (273 files, 0 errores) |

> Los intentos fallidos (02, 02b–02d, 05) quedan registrados a propósito: cada fallo se
> corrigió y se re-evidenció con nombre nuevo, sin debilitar validaciones.

## Qué se implementó

| Archivo | Rol |
|---|---|
| `src/infrastructure/medallion/split_guard.py` | `ensure_development_day()` fail-closed: solo días completos `[2023-09-09..2025-06-16]` (derivados de `splits/v1.json` congelado) |
| `src/infrastructure/medallion/bronze.py` | Descarga idempotente: `.part` → magic+CRC gzip → SHA-256 → manifest atómico → `os.replace`; mismo hash → SKIP; distinto/sin entrada → `HashConflictError`; base URL restringida a `https://public.bybit.com/spot` (prohíbe `/trading/`); `ensure_marker` exige `LENOVO_DATA` |
| `src/infrastructure/medallion/cli.py` | CLI stdlib (`argparse`): `--dest-dir --symbol --dates --base-url --require-marker`; `SUMMARY downloaded=N skipped=M`; exit 0/1/2 |
| `src/infrastructure/medallion/__init__.py` | Export público de la capa |
| `tests/test_bronze_ingest.py` | 30 unit tests (sin red): idempotencia, `.part` stale, hash conflict fail-closed, gzip inválido sin residuo, path traversal, base `/trading/`, manifest determinista, split guard vs `splits/v1.json`, marker, CLI |

Decisiones: solo **stdlib** (`urllib`, `gzip`, `hashlib`, `json`) para ejecutar en el
Python del sistema de lenovosrv sin venv ni Dependency Proposal. Los tiempos operativos
viven SOLO en `ops-downloads.jsonl`; `manifest.json` es determinista (claves ordenadas,
sin timestamps) para comparación byte a byte entre corridas.

## UAT en lenovosrv (3 días consecutivos)

- Destino: `/srv/data/medallion/bronze/bybit/spot/ETHUSDT/date=YYYY-MM-DD/<file>` (HDD `/srv/data`, marker verificado)
- RUN1 (`2024-06-01,02,03`): `downloaded=3` — sha256 `f5dd2cc8…`, `ca1a6b37…`, `f13105db…`
- RUN2 (idéntico): `downloaded=0 skipped=3` — mismos hashes; manifest `cmp` idéntico; sin `.part` residuales
- Fidelidad: hash de `2024-06-01` == muestra canónica descubierta en M3-00; gzip CRC válido con 402 115 líneas
- Fail-closed: `2025-06-17` (WF), `2023-09-08` (pre-DEV), `2026-03-15` (holdout) → exit 1 **antes de la red** y sin crear particiones

## Condiciones de la regla M3 (post-ejecución)

1. Bronze bajo `/srv/data/medallion/bronze/bybit/spot/ETHUSDT` con layout `date=…` — PASS
2. Idempotencia real (RUN2 = 0 descargas, hashes/manifest idénticos) — PASS
3. Split guard DEVELOPMENT-only, fail-closed, antes de la red — PASS
4. Manifest determinista sin timestamps; ops en archivo separado — PASS
5. Nuevas dependencias = 0 (stdlib) — PASS
6. Sin commit / sin push / sin bulk (solo 3 días + 1 muestra) — PASS
7. Calidad repo (ruff/format/mypy/tests) en verde — PASS

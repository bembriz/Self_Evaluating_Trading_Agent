# Commit Candidate Report — 2026-09-27

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

Cerrar M1-B (evidencia del reformato del HDD a ext4 `LENOVO_DATA`, montaje en `/srv/data` y restore de GastosIA) y M1-C (alineación de plantillas/repos con el storage nuevo, sin deploy), y registrar en el ledger `23/m1-storage` como completado.

## Rama

| Campo | Valor |
|---|---|
| branch | `medalion` |
| base commit | `4d4a9bd67f75a29b6fdebd17a36bd545b62b7177` (= `origin/medalion`) |

## Archivos

- **Creados (42):** `docs/phases/23/evidence/m1b-*.log|.sh` (12 pasos + 2 dbg), `docs/phases/23/evidence/m1c-0{1..7}*.log|.sh` (8 evidencias), `docs/phases/23/m1-b-storage-reformat.md`
- **Modificados (2):** `docs/phases/23/evidence/log.md` (índice de evidencias), `harness/state/progress.yaml` (`23/m1-storage` → `done`, vía `progress.py mark-done`)
- **Eliminados:** ninguno

## Diff

```bash
$ git diff --cached --stat
 44 files changed, 2190 insertions(+), 2 deletions(-)
# 42 archivos bajo docs/phases/23/evidence/ + doc de hito + ledger
# (más este commit-candidate → 45 al momento del commit)
$ git diff --cached --check
# único hallazgo: trailing whitespace DENTRO de *.log de evidencia cruda
# (salida verbatim de mkfs/docker/pytest — no editable); 0 hallazgos fuera de ellos
```

## Arquitectura afectada

- Ningún módulo de código: `src/`, `tests/` y `pyproject.toml` intactos (`git status --porcelain src/` = 0).
- Blast radius: 0 símbolos — solo docs, evidencia y ledger de fase.
- Infra del servidor (fuera de git): plantilla `/srv/docker/gastos-ia/repo/deployment/docker/compose.yaml` actualizada y validada en M1-C **sin deploy**; compose activo no tocado.

## Índice del grafo

- [x] Índice re-indexado (`index_repository`, 2026-09-27, moderate → 20 094 nodos / 43 851 aristas, `status=indexed`)
- [x] Cobertura verificada (`check_index_coverage` sobre `progress.yaml`, doc e `log.md` → `no_recorded_issue`; `docs/` excluido del índice por diseño)

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| `ruff check .` | PASS (exit 0) | `m1c-04-ruff-check.log` |
| `ruff format --check .` | PASS (exit 0) | `m1c-04b-ruff-format.log` |
| `mypy src tests` | PASS (exit 0) | `m1c-07-mypy.log` |
| `pytest harness/tests --cov --cov-fail-under=80` | exit=1 **pre-existente**: 2 fallos en `test_gen_pdf` (faltan dev-deps `markdown`/`weasyprint`, sin DP) | `m1c-05-harness-tests.log` |
| `pytest harness/tests --ignore=test_gen_pdf` | PASS (exit 0) — incluye `test_ledger`/`test_progress_cli` (validan el edit del ledger) | `m1c-05b-harness-tests-without-pdf.log` |
| `pytest tests -q` | exit=1 **pre-existente**: 15 errores solo en `tests/integration` (PG 127.0.0.1:5433 caído) | `m1c-06-product-tests.log` |
| `pytest tests -q --ignore=tests/integration` | PASS (exit 0), 100 % de puntos, 1 skip | `m1c-06b-product-unit-tests.log` |

## Cobertura

- Harness suite con `--cov-fail-under=80`: **33.29 %** — por debajo del umbral **de forma pre-existente** (mismo fallo en `m0i-14` de esta fase; los faltantes son los scripts phase18–20 sin tests, no tocados por este commit).
- Unit producto: sin `--cov` en esta ronda (src intacto); baseline fase 16 en `docs/phases/16/evidence/coverage.json`.

## Calidad

```bash
uv run ruff check .          # PASS (exit 0)
uv run ruff format --check . # PASS (exit 0)
uv run mypy src tests        # PASS (exit 0)
uv run pytest tests -q --ignore=tests/integration  # PASS (exit 0)
```

## Seguridad

- [x] Sin secretos en el diff (búsqueda literal de credencial + patrones genéricos: 0 hits)
- [x] Sin archivos `.env` ni credenciales (los logs usan solo la referencia `$SUDO_PASS`)
- [x] Secret scanning limpio en archivos cambiados
- [x] Hallazgo histórico documentado sin exponer valor: "Credencial sudo histórica detectada en evidencia ya versionada. Rotación requerida y limpieza de historial pendiente en gate separado."

## Riesgos

- Bajo: commit de documentación/ledger. El único cambio funcional externo (plantilla server) ya está aplicado y validado fuera de git; este commit no despliega nada.
- `progress.yaml` fue editado exclusivamente por `progress.py mark-done` (tests del ledger en verde).

## Deuda técnica

- Dev-deps `markdown`/`weasyprint` para `test_gen_pdf` requieren Dependency Proposal.
- Tests de integración requieren PostgreSQL local (:5433) levantado.
- Rotación de credencial sudo histórica + limpieza de historial → gate separado.
- Refs `/mnt/warehouse` en `GastoBot` local (fuera de alcance SETA).

## Mensaje de commit propuesto

```
docs(phase-23): M1-B storage + M1-C alineación de repos

- evidencia M1-B: HDD → ext4 LENOVO_DATA /srv/data + restore GastosIA (12 pasos PASS)
- M1-C: plantilla compose server → /srv/data/gastosia, compose config PASS, prod intacto
- ledger: 23/m1-storage → done (vía progress.py mark-done)
- calidad: ruff/mypy/unit verdes; fallos pre-existente documentados (gen_pdf deps, PG integración)
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

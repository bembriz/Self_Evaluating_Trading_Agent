# Commit Candidate Report — 2026-09-27

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).
> Generado por el gate **M0-I — Revalidación de infraestructura lenovosrv (read-only)**.

## Objetivo

Registrar la evidencia formal de M0-I (revalidación READ-ONLY de la infraestructura real de
lenovosrv contra la arquitectura aprobada en M0) y marcar el entregable
`23/m0i-infra-discovery` como DONE en el ledger con rutas de evidencia reales.
Incluye la **corrección r2 de la estimación de capacidad de backup** (alcance M0-II
completo con legados → 395,09 GiB libres tras backup, antes 416,6 GiB inconsistente).

Sin cambios de código del producto; sin cambios de runtime; sin acciones destructivas.

## Rama

| Campo | Valor |
|---|---|
| branch | `medalion` |
| base commit | `12e988eb903585d06a99391e0614a980fd2c1e9c` (= `origin/medalion`, limpio al inicio) |

## Archivos

- **Creados (26):**
  - `docs/phases/23/m0-i-infrastructure-revalidation.md` (reporte del gate, 19 secciones)
  - `docs/phases/23/commit-candidate-001.md` (este archivo)
  - `docs/phases/23/evidence/log.md` (índice, 21 entradas)
  - `docs/phases/23/evidence/m0i-01-host-identity.log`
  - `docs/phases/23/evidence/m0i-02-storage-inventory.log`
  - `docs/phases/23/evidence/m0i-03-nvme-fast-tier.log`
  - `docs/phases/23/evidence/m0i-04-hdd-warehouse.log`
  - `docs/phases/23/evidence/m0i-05-docker-inventory.log`
  - `docs/phases/23/evidence/m0i-06-postgres-topology.log`
  - `docs/phases/23/evidence/m0i-07-proxy-monitoring.log`
  - `docs/phases/23/evidence/m0i-07b-proxy-monitoring-fix.log`
  - `docs/phases/23/evidence/m0i-08-gastosia.log`
  - `docs/phases/23/evidence/m0i-09-paper-certification.log`
  - `docs/phases/23/evidence/m0i-10-global-governance.log`
  - `docs/phases/23/evidence/m0i-11-tier-paths-feasibility.log`
  - `docs/phases/23/evidence/m0i-12-acceptance-check.log`
  - `docs/phases/23/evidence/m0i-12b-acceptance-check.log`
  - `docs/phases/23/evidence/m0i-13-harness-tests.log`
  - `docs/phases/23/evidence/m0i-13b-harness-tests-without-pdf.log`
  - `docs/phases/23/evidence/m0i-14-harness-coverage.log`
  - `docs/phases/23/evidence/m0i-14b-harness-coverage-project.log`
  - `docs/phases/23/evidence/m0i-15-gastosia-backup-sizing.log`
  - `docs/phases/23/evidence/m0i-capacity-correction.log`
  - `docs/phases/23/evidence/m0i-16-correction-validation.log`
  - `docs/phases/23/evidence/coverage.json`
  - `docs/phases/23/evidence/coverage-harness.json`
- **Modificados (1):** `harness/state/progress.yaml` (+9 −3)
- **Eliminados:** ninguno

## Diff

```bash
git diff --stat
# harness/state/progress.yaml | 12 +++++++++---
# 1 file changed, 9 insertions(+), 3 deletions(-)

git diff harness/state/progress.yaml
# meta.actualizado: 2026-09-24 → 2026-09-27
# 23/m0i-infra-discovery: estado pending → done
#   evidencia: [docs/phases/23/evidence/log.md,
#               docs/phases/23/m0-i-infrastructure-revalidation.md]
# time_log: + evento done m0i-infra-discovery (2026-09-27)
```

Los 23 archivos nuevos están sin stagear (`git status`: `?? docs/phases/23/`); el único
tracked modificado es `progress.yaml`, mutado **exclusivamente** vía
`progress.py mark-done` (ledger `mutacion_solo_scripts: true`; YAML validado con
`yaml.safe_load`).

## Arquitectura afectada

- **Ningún módulo de `src/`** — cero impacto en el producto, riesgo, LLM ni ejecución.
- Estado del arnés: `harness/state/progress.yaml` (esquema inalterado; consumidores
  `progress.py`, `gate_check.py`, `gen_report.py` leen el mismo formato).
- Documentación de fase 23 (nueva): reporte M0-I + evidencia.
- Blast radius (codebase-memory `detect_changes`, scope=files): `seed_symbols: 0`;
  los únicos nodos tocados son el ledger y docs.

## Índice del grafo

- [x] Cobertura verificada **pre-cambio** sobre archivos a tocar (`check_index_coverage`:
  `evidence.sh`, `progress.py`, `progress.yaml`, diseño + ADR-0006/0007 → `no_recorded_issue`)
- [ ] Re-indexar tras el commit autorizado (`index_repository`) + `check_index_coverage`
  sobre los 24 archivos — **pendiente post-commit** (AGENTS.md §4.13)

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| `uv run pytest harness/tests -q` | 67 passed · **2 failed** (preexistentes: `test_gen_pdf` sin dev-deps `markdown`/`weasyprint`; mismos fallos documentados en fase 16) | `docs/phases/23/evidence/m0i-13-harness-tests.log` |
| `uv run pytest harness/tests -q --ignore=harness/tests/test_gen_pdf.py` | **67 passed, exit=0** | `docs/phases/23/evidence/m0i-13b-harness-tests-without-pdf.log` |
| Verificación de aceptación M0-I (16 aserciones locales) | exit=0 | `docs/phases/23/evidence/m0i-12b-acceptance-check.log` |
| Corrección de capacidad (recálculo alcance completo, rango 395–396 GiB) | exit=0 | `docs/phases/23/evidence/m0i-capacity-correction.log` |

No aplica: unit/integration/E2E del producto (`src/`) — este cambio no toca `src/`.

## Cobertura

- Arnés con `--cov=harness/scripts --cov-branch`: **33,75%** (1876 statements) —
  **deuda preexistente**, no introducida por este cambio:
  - ~1.116 statements de scripts one-off `phase18*/19*/20*_development_*`,
    `preflight_guards.py` y `release_check.py` nunca tuvieron tests
    (bajada de ~79,6% en fase 16 → hoy).
  - Núcleo del arnés sano: `ledger 90,8% · progress 97,5% · gate_check 96,3% ·
    gen_report 95,9% · new_phase 95,7% · paper_certification 94,8%`.
  - Este diff solo añade docs y muta `progress.yaml` por script → impacto nulo en coverage.
- Artefactos: `docs/phases/23/evidence/coverage.json`, `coverage-harness.json`.

```bash
uv run ruff check . / ruff format --check .   # N/A: sin cambios .py (docs + YAML)
uv run mypy src tests                          # N/A: sin cambios .py
uv run pytest harness/tests                    # ver tabla anterior
```

## Seguridad

- [x] Sin secretos en el diff (grep api_key/secret/token/password/PRIVATE KEY sobre
      `docs/phases/23/` + `progress.yaml` → solo falsos positivos de texto: mensajes
      "a password is required" y descripciones de entregables)
- [x] Sin archivos `.env` ni credenciales
- [x] Evidencia remota recolectada **sin imprimir valores de env** (templates `docker
      inspect` sin `.Config.Env`; `psql -U "$POSTGRES_USER"` sin expandir en claro;
      Caddyfile sin credenciales)
- [x] Secret scanning limpio

## Riesgos

- **Bajo.** Documentación + estado del arnés. El único riesgo operativo es que el ledger
  declare DONE un entregable cuya evidencia debe permanecer inmutable: los logs de
  evidencia no se editarán retroactivamente (regla `gestion-evidencias`).
- La deuda de coverage del arnés queda documentada en el reporte M0-I §15 (no la introduce
  este commit; su solución exige proposal de tests/limpieza de scripts one-off aparte).

## Deuda técnica

1. `test_gen_pdf` roto por dev-deps faltantes (`markdown`, `weasyprint`) — requiere
   Dependency Proposal (infra-control) para `uv add --dev`; NO instalado en M0-I.
2. Coverage del arnés 33,75%: scripts one-off phases 18–20 sin tests (~1.116 stmts).
3. `release_check.py` a 21,5%.

## Mensaje de commit propuesto

```
docs(phase-23): record lenovosrv infrastructure revalidation

- M0-I read-only: host, discos por by-id, tiers NVMe/HDD, docker, PG,
  redes, Caddy, monitoring, GastosIA y aislamiento de la certificación
- 21 logs de evidencia vía evidence.sh + reporte con campos normalizados
- ledger 23/m0i-infra-discovery → done con evidencia real (progress.py)
- aceptación 14/14 PASS; sin acciones destructivas ni cambios de runtime
- corrección r2 de capacidad: backup con alcance completo (activo+legados
  +config/BD/docker) = 21.60 GiB → 395.09 GiB libres tras backup (GiB)
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

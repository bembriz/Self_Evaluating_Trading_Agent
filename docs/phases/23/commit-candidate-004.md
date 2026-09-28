# Commit Candidate Report — 2026-09-27

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

Registrar M2 (Shared Platform Foundation): creación de la base de plataforma compartida en lenovosrv (`/srv/docker/platform`, `/srv/fast/medallion/*`, red externa `platform-net`) sin migrar servicios productivos, la estructura mínima del repo `deployment/platform/` y la marca `23/m2-platform` = done en el ledger.

## Rama

| Campo | Valor |
|---|---|
| branch | `medalion` |
| base commit | `47317b5d4187062461d84dbb354bba820d6e1ac9` (= `origin/medalion`) |

## Archivos

- **Creados (19):**
  - `deployment/platform/compose.yaml` — compose base, `platform-postgres` bajo `profiles: ["platform"]` (inerte), red externa `platform-net`
  - `deployment/platform/README.md` — doc de `platform-net`, tiers y reglas de migración
  - `docs/phases/23/m2-platform-foundation.md`
  - `docs/phases/23/evidence/m2-*.{log,sh}` — 11 evidencias (incluye intentos fallidos documentados: m2-01, m2-02 guard-abort, m2-02c one-liner, m2-04)
- **Modificados (2):** `docs/phases/23/evidence/log.md`, `harness/state/progress.yaml` (`23/m2-platform` → `done` vía `progress.py mark-done`)
- **Eliminados:** ninguno

## Diff

```bash
$ git diff --cached --stat
 21 files changed, 496 insertions(+), 2 deletions(-)
$ git diff --cached --check
rc=0   # 0 hallazgos (esta vez ni siquiera en logs de evidencia)
```

## Arquitectura afectada

- Ningún módulo de código (`src/`, `tests/` intactos; solo docs/evidencia/ledger + 2 archivos nuevos de config).
- lenovosrv (fuera de git): creados directorios y la red `platform-net` (0 contenedores); **cero** servicios migrados/reiniciados — IDs y `StartedAt` de postgres/grafana/prometheus/caddy/GastosIA idénticos al baseline; paper-runner intocado.
- Alineado con ADR-0006 y `docs/design/medallion-replay-architecture.md` (storage + redes).

## Índice del grafo

- [ ] Índice re-indexado tras el commit (`index_repository`) — pendiente post-commit
- [ ] Cobertura verificada sobre archivos tocados (`check_index_coverage`) — `docs/` excluido del índice por diseño; `progress.yaml` sin issues en la verificación de M1

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| `docker compose -f deployment/platform/compose.yaml config -q` | PASS (servicios inertes sin perfil) | `m2-05-repo-compose.log` |
| `pytest harness/tests/test_ledger.py harness/tests/test_progress_cli.py -q` | PASS (39 tests) | `m2-06-ledger-tests.log` |
| `ruff check .` | PASS | verificado en precheck de este candidato |
| Validación remota completa (dirs/tiers/red/contenedores) | PASS | `m2-04b-validate.log` |

## Cobertura

- Sin código Python nuevo/modify → cobertura N/A en este commit (sin cambios en `src/` ni `harness/scripts/`).

## Calidad

```bash
uv run ruff check .                      # All checks passed!
docker compose -f deployment/platform/compose.yaml config -q   # PASS
```

## Seguridad

- [x] Sin secretos en el diff (búsqueda literal: 0 hits)
- [x] Sin archivos `.env` ni credenciales; password de `platform-postgres` solo por `${PLATFORM_PG_PASSWORD:-}`
- [x] Credenciales de servidor en evidencia m2: solo `$SUDO_PASS` literal

## Riesgos

- Bajo: commit de docs/config. La red `platform-net` ya existe en el servidor (creada por instrucción del usuario, 0 adjuntos); el compose del repo es inerte sin `--profile platform`.
- El ledger solo fue editado por `progress.py` (tests en verde).

## Deuda técnica

- Migraciones de postgres/prometheus/grafana/caddy a plataforma → gates futuros (NO en M2).
- Preexistente: rotación de credencial sudo histórica y limpieza de historial (gate separado).
- `docker ps` local sin daemon (no requerido para `compose config`).

## Mensaje de commit propuesto

```
docs(phase-23): M2 platform foundation (dirs, platform-net, repo base)

- lenovosrv: /srv/docker/platform + /srv/fast/medallion/* (NVMe) con guards UUID/marker
- red externa platform-net creada con 0 contenedores; cero migraciones (IDs/StartedAt intactos)
- deployment/platform/: compose base inerte (profile platform) + README de platform-net
- ledger: 23/m2-platform → done (vía progress.py mark-done)
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

# Commit Candidate Report — 2026-09-10 · 16c.7 deployment config/plan 0.2.0

> Obligatorio antes de `git commit` (PRD §65-66). Estado: **READY_FOR_USER_COMMIT_GATE**
> (no se ha ejecutado commit/push/merge).

## Objetivo

Cerrar los blockers del `DEPLOYMENT PREFLIGHT 0.2.0` mediante configuración de deployment,
sin tocar código de producto:

1. Identidad de artefacto **fail-fast** (`GIT_COMMIT` / `DOCKER_IMAGE_DIGEST` inyectados, sin hardcodear).
2. Safeguard evidence en ruta persistente host-backed (`./safeguard` → `/app/safeguard`).
3. Prometheus con target de certificación `paper-runner:9090`, retention ≥45d y solo loopback.
4. Plan de APPLY con orden exacto, instalación explícita de config en producción, rollback por paso y ABORT.
5. Cerrar el trap `PAPER_MAX_RUNTIME_DAYS=7` (insuficiente para la ventana de 30d).

## Rama / base

| Campo | Valor |
|---|---|
| branch | `chore/deployment-preflight-0.2.0` |
| base commit | `8188e8574261febf05875c7ab15da5ff223c3914` (base histórica 16c) |
| PR destino | `feature/phase-08-llm-decision-agent` |
| `FINAL_DEPLOY_SHA` | `<se captura tras el merge de este commit>` |

## Archivos

- **Creados:**
  - `docs/phases/16c/deployment-preflight-0.2.0.md`
  - `docs/phases/16c/deployment-apply-plan-0.2.0.md`
  - `docs/phases/16c/commit-candidate-009.md` (este reporte)
- **Modificados:**
  - `compose.yaml` (identidad fail-fast, safeguard mount, runtime/session, image tag)
  - `deploy/prometheus.yml` (target `paper-runner:9090`)
  - `.env.example` (identidad vacía, `PAPER_MAX_RUNTIME_DAYS=45`, retention)
- **Eliminados:** ninguno.

## Diff

```text
 .env.example                          | 17 ++++++++++++++++-
 compose.yaml                          | 18 ++++++++++++++++++
 deploy/prometheus.yml                 |  6 +++++-
 3 files changed, 39 insertions(+), 2 deletions(-)
 (+ 3 docs nuevas sin trackear)
```

Diff clave:
```diff
# compose.yaml
+    image: self-evaluating-trading-agent-paper-runner:${APP_VERSION:-0.2.0}
+      PAPER_REPORT_INTERVAL_HOURS: ${PAPER_REPORT_INTERVAL_HOURS:-6}
+      PAPER_MAX_RUNTIME_DAYS: ${PAPER_MAX_RUNTIME_DAYS:-45}
+      PAPER_SESSION_ID: ${PAPER_SESSION_ID:-paper-baseline-15m-ethusdt-0.2.0}
+      GIT_COMMIT: "${GIT_COMMIT:?GIT_COMMIT is required - inject final deployed SHA}"
+      DOCKER_IMAGE_DIGEST: "${DOCKER_IMAGE_DIGEST:?DOCKER_IMAGE_DIGEST is required - inject actual deployed image digest}"
+      PAPER_SAFEGUARD_EVIDENCE_PATH: /app/safeguard/safeguard-evidence.json
+      - ./safeguard:/app/safeguard:rw
# deploy/prometheus.yml
-      - targets: ["host.docker.internal:8000", "paper-runner:9090"]
+      - targets: ["paper-runner:9090"]
# .env.example
- PAPER_MAX_RUNTIME_DAYS=7   + 45 ;  GIT_COMMIT= (vacío, inyección obligatoria)
```

## Arquitectura afectada

- **Sin cambios en `src/` ni `tests/`.** Solo configuración de despliegue (`compose.yaml`,
  `deploy/prometheus.yml`, `.env.example`) y documentación (`docs/phases/16c/`).
- Blast radius de producto: **0 símbolos**. No hay cambios de contrato, API, DB ni migraciones.
- Efecto operativo: el `paper-runner` exige identidad de artefacto no vacía al desplegar
  (fail-fast) y monta la evidencia de safeguards.

## Índice del grafo

- [ ] Índice re-indexado tras el commit (`index_repository`) — **pendiente post-commit**
- [ ] Cobertura verificada sobre archivos tocados (`check_index_coverage`) — **pendiente post-commit**
- Nota: los archivos tocados son YAML/MD (no indexados como código); el índice de `src/` no cambia.

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| `docker compose config` (ambos vars) | PASS (exit 0) | esta sesión |
| `docker compose config` (falta `GIT_COMMIT`) | FAIL esperado (exit 1) | esta sesión |
| `docker compose config` (falta `DOCKER_IMAGE_DIGEST`) | FAIL esperado (exit 1) | esta sesión |
| `pytest -k "not_started or restart or legacy or certification or start"` | 25 passed, 19 deselected | esta sesión |
| `pytest tests/e2e/test_certification_state_v2_e2e.py` | 9 passed | esta sesión |
| Prometheus target / retention / exposición | PASS | render + `deploy/prometheus.yml` |

## Cobertura

No aplica: **0 líneas de producto modificadas**. Cobertura de producto y de arnés sin cambio.

## Calidad

```bash
uv run ruff check .          # All checks passed!
uv run ruff format --check . # 268 files already formatted
uv run mypy src tests        # Success: no issues found in 235 source files
uv run pytest                # (no aplica cambios de código; suites dirigidas arriba)
```

## Seguridad

- [x] Sin secretos en el diff
- [x] Sin archivos `.env` reales (solo `.env.example`, con identidad vacía)
- [x] Sin credenciales; `LIVE_TRADING_ENABLED=false`
- [x] Identidad de artefacto obligatoria (fail-fast) para la certificación

## Riesgos

- El commit **no** despliega: requiere el flujo §2 del plan (commit → PR → CI → merge → `FINAL_DEPLOY_SHA`).
- Si el operador no inyecta `GIT_COMMIT`/`DOCKER_IMAGE_DIGEST`, `docker compose config` falla (deseado).
- `.env` productivo no existe hoy; el APPLY lo crea con la identidad (no es secreto).

## Deuda técnica

- `config/paper.yaml` no se carga (solo `config/base.yaml`); su `paper_max_runtime_days: 7` es engañoso. Fuera de alcance.
- `docker logs` de 0.1.3 vacío: verificar driver/logging en runtime validation.
- Healthcheck del paper-runner no definido (mejora opcional futura).

## Mensaje de commit propuesto

```
chore(deploy): 16c.7 config de deployment 0.2.0 + plan APPLY

- compose.yaml: identidad fail-fast GIT_COMMIT/DOCKER_IMAGE_DIGEST (inyectadas, sin hardcodear);
  image tag 0.2.0; PAPER_MAX_RUNTIME_DAYS=45; PAPER_SESSION_ID 0.2.0; safeguard bind mount
- deploy/prometheus.yml: target paper-runner:9090 (retention 45d, loopback sin cambios)
- .env.example: PAPER_MAX_RUNTIME_DAYS 7->45; identidad vacía; PROMETHEUS_RETENTION
- docs/phases/16c: preflight 0.2.0 + plan APPLY (rollback/ABORT) + commit candidate
- sin cambios de producto/tests; Paper sigue NOT CERTIFIED
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:

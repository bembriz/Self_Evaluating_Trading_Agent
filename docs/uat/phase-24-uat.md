# UAT — Fase 24: Automated Medallion Refresh

> Prueba de aceptación de usuario (HITL). El agente NO puede aprobar UAT.
> Ejecutada por el decisor sobre lenovosrv (`administrador@192.168.100.24`).
>
> **Alcance:** verifica el despliegue y operación real del refresh Medallion automático
> (systemd oneshot + timer diario 06:20 UTC), los guards de capacidad/volumen, la
> colección `FUTURE_COLLECTION` desde `2026-08-24` (solo Bronze/Silver/Candles), la
> idempotencia y el no-impacto en Gold/WF/HOLDOUT/paper.
> **No** se modificó `splits/v1.json`, ni el marker real, ni la configuración de paper.
>
> **Revisión aplicada:** `b14aa04be51070c381765a19a9d5b57315833338`
> (`fix(medallion): unblock safe future collection refresh`).

## Precondiciones

| # | Precondición | Verificada |
|---|---|---|
| 1 | `HEAD == origin/main == b14aa04be51070c381765a19a9d5b57315833338`, worktree limpio | SÍ |
| 2 | `/srv/data` montado (`/dev/sda1 ext4`), label `LENOVO_DATA`, UUID `10fff707-60e4-4321-afa0-a3c4704d9e8d` | SÍ |
| 3 | Marker `/srv/data/.lenovosrv-data-volume` = `LENOVO_DATA` | SÍ |
| 4 | NVMe libre 396 GB (≥ `SSD_MIN_FREE_GB=50`); caché `30 MB` (≤ `SSD_CACHE_MAX_GB=64 GB`) | SÍ |
| 5 | `administrador` puede escribir rutas canónicas Medallion y `/srv/fast/medallion` | SÍ |
| 6 | `paper-runner` en ejecución (no se reinicia ni se toca) | SÍ |

## Entradas / Datos

- Revision staged: `git archive b14aa04 src deployment/medallion/systemd` (sha256 `80e6fda6…`), extraída en `/tmp/seta-medallion-b14aa04`.
- Runtime instalado: `/opt/seta-medallion/src` (`root:root`, dirs `0755`, files `0644`).
- Fechas: servidor `2026-09-30 UTC` ⇒ `target_day = 2026-09-29` (FUTURE_COLLECTION).
- Histórico pre-aplicación: Bronze 647 días, Silver trades 647, Silver candles 4529 archivos.

## Pasos

### Paso 1 (S) — Instalación systemd

```bash
sudo bash /tmp/seta-medallion-b14aa04/deployment/medallion/systemd/install.sh
systemctl is-enabled medallion-refresh.timer   # enabled
systemctl is-active  medallion-refresh.timer   # active
systemctl list-timers medallion-refresh.timer --no-pager
```

**Resultado esperado:** runtime en `/opt/seta-medallion`, unidades instaladas, timer
`enabled`+`active`, próxima ejecución ±06:20 UTC con `RandomizedDelaySec=15m`.

### Paso 2 (S) — Primera ejecución real

```bash
sudo systemctl start medallion-refresh.service
systemctl show medallion-refresh.service -p Result -p ExecMainStatus
cat /srv/fast/medallion/refresh/status.json
```

**Resultado esperado:** `Result=success`, `ExecMainStatus=0`, `result=OK`, solo días
FUTURE_COLLECTION añadidos a Bronze/Silver/Candles, Gold sin cambios, sin `.part`.

### Paso 3 (S) — Segunda ejecución (idempotencia)

```bash
sudo systemctl start medallion-refresh.service
```

**Resultado esperado:** `result=OK_NOOP`, `planned=0`, `executed=0`, hashes/manifiestos
canónicos sin cambios, sin entradas duplicadas.

### Paso 4 (S) — Guards negativos (config sintética aislada; marker real intacto)

```bash
PYTHONPATH=/opt/seta-medallion/src python3 - <<'PY'
# probes sintéticos: marker inválido, label erróneo, UUID mismatch, no-mountpoint,
# free space insuficiente, WF, HOLDOUT, 2026-08-23, FUTURE sin scope; positivo 2026-08-24
PY
```

### Paso 5 (L) — Calidad automatizada

```bash
uv run pytest tests/test_medallion_future_collection.py tests/test_medallion_refresh.py \
  tests/test_medallion_capacity_guards.py tests/test_medallion_systemd_units.py \
  tests/test_bronze_ingest.py tests/test_silver_trades.py tests/test_silver_candles.py \
  tests/test_source_schema.py tests/test_gold_dataset.py -q
```

## Evidencia a adjuntar

- `docs/phases/24/evidence/p24-uat-systemd-state.log`
- `docs/phases/24/evidence/p24-uat-status-json.log`
- `docs/phases/24/evidence/p24-uat-journal.log`
- `docs/phases/24/evidence/p24-uat-canonical-idempotency.log`
- `docs/phases/24/evidence/p24-uat-negative-guards.log`
- `docs/phases/24/evidence/p24-uat-paper-safety.log`
- `docs/phases/24/evidence/p24-uat-gold-unchanged.log`

## Resultado observado

### Runtime / systemd

| Item | Observado | ¿Coincide? |
|---|---|---|
| Runtime | `/opt/seta-medallion/src` `root:root`, dirs `0755`, files `0644`; `IMPORT_OK` como `administrador` | SÍ |
| Timer | `enabled` + `active` | SÍ |
| Próxima ejecución | `06:20 UTC` + `RandomizedDelaySec=15m` (p. ej. `06:33:14 UTC`) | SÍ |
| Servicio | `Type=oneshot`; tras ejecución `ActiveState=inactive`/`dead`, `Result=success` | SÍ |

### Primera ejecución

| Métrica | Observado | ¿Coincide? |
|---|---|---|
| `result` | `OK` | SÍ |
| `planned` / `executed` / `completed` | `111` / `111` / `111` (37 días × 3 capas) | SÍ |
| Días FUTURE_COLLECTION | `2026-08-24 … 2026-09-29` (37) | SÍ |
| Bronze | `647 → 684` días | SÍ |
| Silver trades | `647 → 684` días | SÍ |
| Silver candles | `4529 → 4788` archivos (+259) | SÍ |
| `blocked_days` | `[]` | SÍ |
| `gold_blocked_days` | `37` | SÍ |
| `UNASSIGNED_RESEARCH_READS` | `0` | SÍ |
| WF/HOLDOUT reads | `0` | SÍ |
| `.part` leftovers | `0` | SÍ |

### Segunda ejecución (idempotencia)

| Métrica | Observado | ¿Coincide? |
|---|---|---|
| `result` | `OK_NOOP` | SÍ |
| `planned` / `executed` | `0` / `0` | SÍ |
| Bronze manifest (684) sha256 | `8d680b4c…c7ba` sin cambios | SÍ |
| Silver trades manifest (684) sha256 | `96e63de2…6881` sin cambios | SÍ |
| Silver candles manifest (4788) sha256 | `8f3286f0…96da` sin cambios | SÍ |
| Duplicados en manifiesto | ninguno | SÍ |

### Guards (fail-closed)

| Caso | Observado |
|---|---|
| marker inválido (vacío) | `BLOCKED CapacityGuardError` |
| label erróneo | `BLOCKED CapacityGuardError` |
| UUID mismatch | `BLOCKED CapacityGuardError` |
| no-mountpoint | `BLOCKED CapacityGuardError` |
| free space insuficiente | `BLOCKED CapacityGuardError` |
| WALK_FORWARD (`2025-06-17`) | `BLOCKED SplitGuardError` |
| FINAL_HOLDOUT (`2026-03-15`) | `BLOCKED SplitGuardError` |
| `2026-08-23` | `BLOCKED SplitGuardError` |
| FUTURE sin scope explícito | `BLOCKED SplitGuardError` |
| `2026-08-24` con scope | `ALLOWED` |
| Marker real | `LENOVO_DATA` (intacto) |

### Seguridad paper / Gold

| Item | Observado | ¿Coincide? |
|---|---|---|
| Container ID | `b061332c35724a2147df3c76acdd8ba4cace12157b958766e2d66cb3f34e22bb` (igual) | SÍ |
| Image | `self-evaluating-trading-agent-paper-runner:0.2.0` | SÍ |
| StartedAt | `2026-09-19T04:00:04.763010163Z` (igual) | SÍ |
| Running | `true` | SÍ |
| RestartCount | `3` (sin cambios) | SÍ |
| Mounts | `safeguard`/`reports`/`certification` sin cambios | SÍ |
| Gold | `gold-replay-5ca68f44…`, `gold-replay-a8c49e0b…`, `ops-gold.jsonl` sin cambios (0 archivos modificados desde el apply) | SÍ |

### Calidad automatizada

- Focal Medallion: `253 passed`.
- Suite unitaria completa: `1299 passed, 1 skipped`.
- Cobertura unitaria `90.56%` (≥ 90).
- `ruff check` / `ruff format --check` / `mypy src tests`: PASS.
- `systemd-analyze verify`: PASS.

## Incidencias encontradas

Ninguna. La remediación previa (`b14aa04`) eliminó los 3 blockers de preflight:
runtime path, `MEDALLION_START_DAY`, y `MEDALLION_BRONZE_DIR`; además habilitó el guard
explícito de FUTURE_COLLECTION.

---

## VEREDICTO UAT: APPROVED
Decisor: usuario (bembriz)  Fecha: 2026-09-30
Comentario: Apply, primera ejecución FUTURE_COLLECTION, idempotencia, guards negativos y no-impacto en Gold/WF/HOLDOUT/paper verificados en lenovosrv. Rollback no requerido.

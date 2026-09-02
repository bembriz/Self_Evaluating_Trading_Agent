# Spec — Paper Runner Periodic Reports (Fase 16)

> **Estado:** draft aprobado en brainstorming (2026-09-01)
> **Fuente de verdad del producto:** PRD §45 (métricas), fase 16 (certificación paper).

## Problema

El `paper-runner` desplegado en `lenovosrv` solo persiste eventos crudos en `paper_trade_events`. No emite reportes periódicos ni actualiza el estado de certificación: `summarize_events`, `write_periodic_report` y `write_certification_state` existen en `src/application/services/paper_runner.py` pero nadie los llama; `report_interval_seconds` se configura y se ignora. El entregable `informes-periodicos` del ledger estaba marcado done sin reportes reales (corregido a blocked).

## Objetivo

Que el runner emita un reporte periódico a archivo cada `report_interval_seconds` (24h desde el arranque del contenedor) con las métricas de la sesión **ampliadas con delta diario y PnL**, y que actualice `certification-state.json`. Los reportes quedan accesibles en el server mediante bind-mount, sin entrar al contenedor.

## Decisiones de diseño

- **Reporte a archivo** (no endpoint HTTP ni tabla extra). Reutiliza las funciones existentes.
- **Cada 24h desde el arranque** del proceso (usa `report_interval_seconds` ya configurado; no alineado a medianoche UTC).
- **Ampliar contenido**: mantener lo que produce `summarize_events` + añadir PnL absoluto/%, delta desde el reporte anterior y PnL del delta.
- **No romper el bucle** ante fallos de escritura: log + continuar.
- **Mantener capas**: el emisor vive en el CLI (composition root), no en `PaperRunner`; `PaperRunner.run_once` sigue siendo stub.

## Cambios

### 1. `src/application/services/paper_runner.py`

Ampliar `PaperRunSummary` con campos nuevos y `summarize_events` con soporte de reporte previo:

```python
@dataclass(frozen=True, slots=True)
class PaperRunSummary:
    session_id: str
    decision_source: str
    strategy_version: str
    strategy_hash: str
    symbol: str
    timeframe: str
    first_timestamp_ms: int | None
    latest_timestamp_ms: int | None
    decisions: dict[str, int]
    fills: int
    fees: float
    slippage: float
    latest_equity: float
    kill_switch_active: bool
    initial_equity: float = 1000.0
    pnl_absolute: float = 0.0      # latest_equity - initial_equity
    pnl_pct: float = 0.0           # pnl_absolute / initial_equity
    delta_decisions: dict[str, int] | None = None   # solo si previous dado
    delta_fills: int | None = None
    delta_pnl_absolute: float | None = None
    delta_pnl_pct: float | None = None
```

- `summarize_events(events, previous: PaperRunSummary | None = None, *, initial_equity: float = 1000.0)`:
  - `initial_equity` se recibe por parámetro (el CLI lo inyecta desde `RiskConfig().capital`); el dataclass lo expone. No se infiere de los eventos (no es fiable).
  - con `previous`: delta de decisions/fills = total - previous; `delta_pnl_absolute = pnl_absolute - previous.pnl_absolute`; `delta_pnl_pct` idem.
- `write_periodic_report(summary, report_path)`:
  - añade líneas `pnl_absolute`, `pnl_pct`, `delta_fills`, `delta_pnl_absolute`, `delta_pnl_pct` (o `n/a` si no hay previo).
  - escribe además el reporte como `paper-<YYYYMMDD-HHMMSS>.md` nombrado por `latest_timestamp_ms` en la ruta de directorio que reciba el CLI.

### 2. `src/settings.py`

```python
paper_report_dir: str = "reports/paper"
paper_certification_state_path: str = "docs/phases/16/certification-state.json"
paper_report_interval_hours: int = 24   # ya existe
```

### 3. `src/interfaces/cli/paper_runner.py`

- En `_run`, dentro del `while`:
  - `last_report_time = loop.time()` al arrancar.
  - al pasar `report_interval_seconds`, recoger `events = await repo.list_session(config.session_id)`, `summary = summarize_events(events, previous=last_summary)`, `write_periodic_report(summary, Path(settings.paper_report_dir) / f"paper-{ts}.md")`, `write_certification_state(summary, Path(settings.paper_certification_state_path), previous_state)`, guardar `last_summary`/`last_report_time`.
  - `initial_equity` se pasa en el summary desde `RiskConfig().capital` (default 1000.0).
- `initial_equity` se inyecta vía `summarize_events(..., initial_equity=...)` (parámetro con default) para que el CLI lo tome de settings/config sin que el servicio importe risk.
- errores de escritura: `try/except OSError` → `print` de warning y continuar.

### 4. `config/paper.yaml` / `.env.example` / `compose.yaml`

- `config/paper.yaml`: `paper_report_dir: reports/paper`, `paper_certification_state_path: docs/phases/16/certification-state.json`.
- `.env.example`: `PAPER_REPORT_DIR=reports/paper`, `PAPER_CERTIFICATION_STATE_PATH=...`.
- `compose.yaml` `paper-runner`: añadir
  ```yaml
  volumes:
    - ./reports:/app/reports:rw
    - ./certification:/app/certification:rw
  ```
  Ambos bind-mounts visibles en el server (`/srv/docker/self-evaluating-trading-agent/reports` y `/srv/docker/self-evaluating-trading-agent/certification`); el state se escribe en `certification/` y el runner usa la ruta relativa configurada.

### 5. Tests

- `tests/test_paper_runner.py`:
  - `test_summarize_events_computes_pnl_from_initial_equity`
  - `test_summarize_events_delta_with_previous`
  - `test_write_periodic_report_includes_pnl_and_delta`
- `tests/test_cli_paper_runner.py`:
  - `test_run_emits_report_after_interval` con fake clock + stream (2 klines separadas por intervalo) y verifica que se crea el `.md` y se actualiza el state json.
- `tests/test_settings.py`: defaults y override por env de `paper_report_dir` y `paper_certification_state_path`.

## Errores y resiliencia

- Escritura de reporte/state falla (`OSError`, permisos, disco): warning a stdout, no detiene el runner.
- `list_session` sin eventos aún: `summarize_events([])` con `initial_equity` dado → summary vacío, no crash.
- Contenedor reinicia: `report_interval_seconds` se re-mide desde el nuevo arranque; no se pierden eventos (persistidos en Postgres).

## Fuera de alcance

- Endpoint HTTP/dashboard de reportes.
- Alineación a medianoche UTC.
- Métricas técnicas (prometheus/grafana) del runner.
- Cambio de `decision_source` (sigue `baseline`).

## Criterios de aceptación

1. El runner desplegado emite `reports/paper/paper-*.md` cada 24h con decisiones, fills, fees, slippage, equity, PnL absoluto/%, y delta vs reporte anterior.
2. `certification-state.json` se actualiza periódicamente y `paper_certification.py` sigue consumiéndolo.
3. Tests unit/CLI/settings verdes; lint + typing verdes.
4. El entregable `informes-periodicos` solo vuelve a `done` con reportes reales del server como evidencia.

# Paper Runner Periodic Reports — Implementation Plan (Fase 16)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el `paper-runner` emita un reporte periódico a archivo cada `report_interval_seconds` (24h desde arranque) con decisiones, fills, fees, slippage, equity, PnL absoluto/% y delta vs reporte anterior, y que actualice `certification-state.json`.

**Architecture:** Ampliar `PaperRunSummary`/`summarize_events` con PnL y delta (servicio, dominio puro), añadir settings de rutas, e integrar la emisión en el bucle del CLI (`src/interfaces/cli/paper_runner.py`) extrayendo un `_run_loop` inyectable para poder testear con fake stream/clock. Mantener capas: el emisor vive en el CLI, `PaperRunner.run_once` sigue siendo stub.

**Tech Stack:** Python 3.12, asyncio, SQLAlchemy async, pytest.

## Global Constraints

- `decision_source = baseline` y `EmaRsiBaseline` se mantienen (no cambia la estrategia).
- `TRADING_MODE=paper` y `LIVE_TRADING_ENABLED=false` son obligatorios (validación ya existente, no debilitar).
- Sin import de `infrastructure.bybit.trade_client`, sin LLM en el runner (restricción ya verificada por `final-forbidden-imports.log`).
- El emisor de reportes NO rompe el bucle ante `OSError`: warning a stdout y continuar.
- `initial_equity` se inyecta por parámetro (el CLI lo toma de `RiskConfig().capital`, default 1000.0); no se infiere de eventos.
- Los campos nuevos del state JSON deben seguir siendo legibles por `harness/scripts/paper_certification.py` (usa `state.get(...)`).
- Comandos de verificación vía `bash harness/scripts/evidence.sh 16 <nombre> -- <cmd>`.
- Sin commit/push sin autorización explícita.

---

### Task 1: PaperRunSummary con PnL y delta + escritores ampliados

**Files:**
- Modify: `src/application/services/paper_runner.py`
- Test: `tests/test_paper_runner.py`

**Interfaces:**
- Consumes: `PaperTradeEvent` (campos existentes: `action`, `filled`, `fee`, `slippage_cost`, `equity`, `session_id`, `timestamp_ms`).
- Produces:
  - `PaperRunSummary` con campos nuevos: `initial_equity`, `pnl_absolute`, `pnl_pct`, `delta_decisions: dict[str,int] | None`, `delta_fills: int | None`, `delta_pnl_absolute: float | None`, `delta_pnl_pct: float | None`.
  - `summarize_events(events, previous: PaperRunSummary | None = None, *, initial_equity: float = 1000.0) -> PaperRunSummary`.
  - `write_periodic_report(summary, report_path: Path) -> None` ampliado.
  - `write_certification_state(summary, state_path, previous: dict | None = None) -> None` ampliado con PnL.

- [ ] **Step 1: Escribir tests que fallan (PnL y delta)**

Append a `tests/test_paper_runner.py`:

```python
def test_summarize_events_computes_pnl_from_initial_equity() -> None:
    events = [
        _paper_event(action="BUY", filled=True, fee=0.10, slippage_cost=0.02, equity=1100.0),
    ]

    summary = summarize_events(events, initial_equity=1000.0)

    assert summary.initial_equity == 1000.0
    assert summary.pnl_absolute == 100.0
    assert summary.pnl_pct == pytest.approx(0.10)
    assert summary.delta_fills is None


def test_summarize_events_delta_with_previous() -> None:
    previous = summarize_events(
        [_paper_event(action="HOLD", filled=False, equity=1050.0)],
        initial_equity=1000.0,
    )
    events = [
        _paper_event(action="HOLD", filled=False, equity=1050.0),
        _paper_event(action="BUY", filled=True, equity=1100.0),
    ]

    summary = summarize_events(events, previous=previous, initial_equity=1000.0)

    assert summary.delta_fills == 1
    assert summary.delta_decisions == {"BUY": 1, "SELL": 0, "HOLD": 0}
    assert summary.delta_pnl_absolute == 50.0
    assert summary.delta_pnl_pct == pytest.approx(0.05)


def test_write_periodic_report_includes_pnl_and_delta(tmp_path: Path) -> None:
    summary = summarize_events(
        [_paper_event(action="BUY", filled=True, equity=1100.0)],
        initial_equity=1000.0,
    )
    report = tmp_path / "paper-report.md"

    write_periodic_report(summary, report)

    text = report.read_text(encoding="utf-8")
    assert "pnl_absolute: 100.0" in text
    assert "pnl_pct: 0.1" in text
    assert "delta_fills: n/a" in text
```

- [ ] **Step 2: Ejecutar los tests y verificar que fallan**

Run: `uv run pytest tests/test_paper_runner.py::test_summarize_events_computes_pnl_from_initial_equity tests/test_paper_runner.py::test_summarize_events_delta_with_previous tests/test_paper_runner.py::test_write_periodic_report_includes_pnl_and_delta -q`
Expected: FAIL (los campos no existen).

- [ ] **Step 3: Ampliar `PaperRunSummary`**

En `src/application/services/paper_runner.py`, reemplazar el dataclass:

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
    pnl_absolute: float = 0.0
    pnl_pct: float = 0.0
    delta_decisions: dict[str, int] | None = None
    delta_fills: int | None = None
    delta_pnl_absolute: float | None = None
    delta_pnl_pct: float | None = None
```

- [ ] **Step 4: Ampliar `summarize_events`**

Reemplazar la firma y el cuerpo para aceptar `previous` e `initial_equity` y calcular PnL/delta:

```python
def summarize_events(
    events: list[PaperTradeEvent],
    previous: PaperRunSummary | None = None,
    *,
    initial_equity: float = 1000.0,
) -> PaperRunSummary:
    decisions = {"BUY": 0, "SELL": 0, "HOLD": 0}
    ordered = sorted(events, key=lambda event: event.timestamp_ms)
    for event in ordered:
        decisions[event.action] = decisions.get(event.action, 0) + 1
    first = ordered[0] if ordered else None
    last = ordered[-1] if ordered else None
    latest_equity = last.equity if last else initial_equity
    pnl_absolute = latest_equity - initial_equity
    pnl_pct = pnl_absolute / initial_equity if initial_equity else 0.0
    if previous is None:
        delta_decisions: dict[str, int] | None = None
        delta_fills: int | None = None
        delta_pnl_absolute: float | None = None
        delta_pnl_pct: float | None = None
    else:
        delta_decisions = {
            action: decisions.get(action, 0) - previous.decisions.get(action, 0)
            for action in ("BUY", "SELL", "HOLD")
        }
        delta_fills = sum(1 for event in ordered if event.filled) - previous.fills
        delta_pnl_absolute = pnl_absolute - previous.pnl_absolute
        delta_pnl_pct = pnl_pct - previous.pnl_pct
    return PaperRunSummary(
        session_id=first.session_id if first else "",
        decision_source=first.decision_source if first else "baseline",
        strategy_version=first.strategy_version if first else "",
        strategy_hash=first.strategy_hash if first else "",
        symbol=first.symbol if first else "",
        timeframe=first.timeframe if first else "",
        first_timestamp_ms=first.timestamp_ms if first else None,
        latest_timestamp_ms=last.timestamp_ms if last else None,
        decisions=decisions,
        fills=sum(1 for event in ordered if event.filled),
        fees=sum(event.fee for event in ordered),
        slippage=sum(event.slippage_cost for event in ordered),
        latest_equity=latest_equity,
        kill_switch_active=last.kill_switch_active if last else False,
        initial_equity=initial_equity,
        pnl_absolute=pnl_absolute,
        pnl_pct=pnl_pct,
        delta_decisions=delta_decisions,
        delta_fills=delta_fills,
        delta_pnl_absolute=delta_pnl_absolute,
        delta_pnl_pct=delta_pnl_pct,
    )
```

- [ ] **Step 5: Ampliar `write_periodic_report`**

Reemplazar el cuerpo para añadir líneas PnL/delta:

```python
def write_periodic_report(summary: PaperRunSummary, report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    delta_fills = summary.delta_fills if summary.delta_fills is not None else "n/a"
    delta_pnl = (
        f"{summary.delta_pnl_absolute:.8f}" if summary.delta_pnl_absolute is not None else "n/a"
    )
    delta_pnl_pct = (
        f"{summary.delta_pnl_pct:.8f}" if summary.delta_pnl_pct is not None else "n/a"
    )
    report_path.write_text(
        "\n".join(
            [
                "# Paper Trading Periodic Report",
                "",
                f"session_id: {summary.session_id}",
                f"decision_source: {summary.decision_source}",
                f"strategy_version: {summary.strategy_version}",
                f"strategy_hash: {summary.strategy_hash}",
                f"symbol: {summary.symbol}",
                f"timeframe: {summary.timeframe}",
                f"first_timestamp_ms: {summary.first_timestamp_ms}",
                f"latest_timestamp_ms: {summary.latest_timestamp_ms}",
                f"buy_decisions: {summary.decisions.get('BUY', 0)}",
                f"sell_decisions: {summary.decisions.get('SELL', 0)}",
                f"hold_decisions: {summary.decisions.get('HOLD', 0)}",
                f"fills: {summary.fills}",
                f"fees: {summary.fees:.8f}",
                f"slippage: {summary.slippage:.8f}",
                f"initial_equity: {summary.initial_equity:.8f}",
                f"latest_equity: {summary.latest_equity:.8f}",
                f"pnl_absolute: {summary.pnl_absolute:.8f}",
                f"pnl_pct: {summary.pnl_pct:.8f}",
                f"delta_fills: {delta_fills}",
                f"delta_pnl_absolute: {delta_pnl}",
                f"delta_pnl_pct: {delta_pnl_pct}",
                f"kill_switch_active: {summary.kill_switch_active}",
                "",
            ]
        ),
        encoding="utf-8",
    )
```

- [ ] **Step 6: Ampliar `write_certification_state`**

Añadir PnL al state sin romper el contrato de `paper_certification.py`:

```python
def write_certification_state(
    summary: PaperRunSummary,
    state_path: Path,
    previous: dict[str, Any] | None = None,
) -> None:
    first = summary.first_timestamp_ms
    latest = summary.latest_timestamp_ms
    calendar_days = 0
    if first is not None and latest is not None:
        calendar_days = max(1, ((latest - first) // 86_400_000) + 1)
    data = dict(previous or {})
    data.update(
        {
            "strategy_version": summary.strategy_version,
            "strategy_hash": summary.strategy_hash,
            "active_strategy_hash": summary.strategy_hash,
            "calendar_days": calendar_days,
            "trade_count": summary.fills,
            "market_regimes": data.get("market_regimes", []),
            "periodic_reports": [
                report
                for report in data.get("periodic_reports", [])
                if isinstance(report, str) and Path(report).exists()
            ],
            "latest_equity": summary.latest_equity,
            "initial_equity": summary.initial_equity,
            "pnl_absolute": summary.pnl_absolute,
            "pnl_pct": summary.pnl_pct,
        }
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
```

- [ ] **Step 7: Ejecutar todos los tests de `test_paper_runner.py`**

Run: `uv run pytest tests/test_paper_runner.py -q`
Expected: PASS (los tests existentes siguen verdes — los campos nuevos tienen defaults; `test_write_certification_state_*` siguen pasando).

- [ ] **Step 8: Evidencia**

Run: `bash harness/scripts/evidence.sh 16 paper-runner-pnl-delta-tests -- uv run pytest tests/test_paper_runner.py -q`
Expected: exit 0.

---

### Task 2: Settings de rutas de reporte

**Files:**
- Modify: `src/settings.py`
- Modify: `config/paper.yaml`
- Modify: `.env.example`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: `Settings` pydantic (patrón existente).
- Produces:
  - `Settings.paper_report_dir: str = "reports/paper"`
  - `Settings.paper_certification_state_path: str = "docs/phases/16/certification-state.json"`

- [ ] **Step 1: Escribir test que falla**

Append a `tests/test_settings.py`:

```python
def test_paper_report_paths_defaults(monkeypatch: MonkeyPatch) -> None:
    for var in ("PAPER_REPORT_DIR", "PAPER_CERTIFICATION_STATE_PATH"):
        monkeypatch.delenv(var, raising=False)

    s = Settings()

    assert s.paper_report_dir == "reports/paper"
    assert s.paper_certification_state_path == "docs/phases/16/certification-state.json"


def test_paper_report_paths_env_override(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PAPER_REPORT_DIR", "custom/reports")
    monkeypatch.setenv("PAPER_CERTIFICATION_STATE_PATH", "custom/state.json")

    s = Settings()

    assert s.paper_report_dir == "custom/reports"
    assert s.paper_certification_state_path == "custom/state.json"
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `uv run pytest tests/test_settings.py::test_paper_report_paths_defaults tests/test_settings.py::test_paper_report_paths_env_override -q`
Expected: FAIL (atributos no existen).

- [ ] **Step 3: Añadir campos a `Settings`**

En `src/settings.py`, tras `paper_max_runtime_days: int = 7`:

```python
    paper_report_dir: str = "reports/paper"
    paper_certification_state_path: str = "docs/phases/16/certification-state.json"
```

- [ ] **Step 4: Actualizar `config/paper.yaml`**

Append:

```yaml
paper_report_dir: reports/paper
paper_certification_state_path: docs/phases/16/certification-state.json
```

- [ ] **Step 5: Actualizar `.env.example`**

Append:

```text
PAPER_REPORT_DIR=reports/paper
PAPER_CERTIFICATION_STATE_PATH=docs/phases/16/certification-state.json
```

- [ ] **Step 6: Ejecutar todos los tests de settings**

Run: `uv run pytest tests/test_settings.py -q`
Expected: PASS.

- [ ] **Step 7: Evidencia**

Run: `bash harness/scripts/evidence.sh 16 paper-runner-settings-tests -- uv run pytest tests/test_settings.py -q`
Expected: exit 0.

---

### Task 3: Emisión periódica en el CLI (`_run_loop` inyectable)

**Files:**
- Modify: `src/interfaces/cli/paper_runner.py`
- Test: `tests/test_cli_paper_runner.py`

**Interfaces:**
- Consumes:
  - `PaperRunnerConfig`, `PaperRunner`, `UnsafePaperModeError` (de `application.services.paper_runner`)
  - `PaperTradeEventRepository` (de `application.ports.paper_trading`)
  - `PaperRunSummary`, `summarize_events`, `write_periodic_report`, `write_certification_state` (de `application.services.paper_runner`)
  - `KlineUpdate` (de `domain.market.stream`)
  - `RiskConfig` (de `domain.risk.config`) — para `capital` como `initial_equity`
- Produces:
  - `_run_loop(*, stream, runner, repo, commit, session_id, report_interval_seconds, report_dir: Path, state_path: Path, initial_equity: float, deadline: float | None) -> str` — coroutine inyectable (todo testeable).
  - `_run(...)` refactorizado para componer y delegar en `_run_loop`.

- [ ] **Step 1: Escribir tests que fallan**

Append a `tests/test_cli_paper_runner.py`:

```python
import asyncio
from pathlib import Path

import pytest

from application.services.paper_runner import (
    PaperRunner,
    PaperRunnerConfig,
    PaperRunSummary,
    summarize_events,
    write_certification_state,
    write_periodic_report,
)
from domain.market.candle import Timeframe
from domain.market.stream import KlineUpdate
from interfaces.cli.paper_runner import _run_loop


class FakeStream:
    def __init__(self, events: list) -> None:
        self._events = list(events)

    async def recv(self):
        if not self._events:
            await asyncio.sleep(0.05)
            return None
        return self._events.pop(0)

    async def connect(self) -> None:
        pass

    async def subscribe_kline(self, symbol: str, timeframe) -> None:
        pass

    async def close(self) -> None:
        pass


class FakeRepo:
    def __init__(self, events: list) -> None:
        self._events = events

    async def add(self, event) -> None:
        self._events.append(event)

    async def list_session(self, session_id: str) -> list:
        return list(self._events)


def _kline(close: float, ts: int, confirm: bool = True) -> KlineUpdate:
    return KlineUpdate("ETHUSDT", Timeframe.M15, ts, close, close, close, close, 10.0, 1000.0, confirm)


def _paper_runner(repo: FakeRepo) -> PaperRunner:
    config = PaperRunnerConfig(
        trading_mode="paper",
        live_trading_enabled=False,
        symbols=("ETHUSDT",),
        timeframe="15m",
        session_id="paper-baseline-test",
        report_interval_seconds=1,
    )
    return PaperRunner(config=config, event_repo=repo)


async def test_run_loop_emits_report_after_interval(tmp_path: Path) -> None:
    repo = FakeRepo([])
    stream = FakeStream([_kline(100.0, 1_000)])
    report_dir = tmp_path / "reports"
    state_path = tmp_path / "certification-state.json"

    async def fake_commit() -> None:
        pass

    runner = _paper_runner(repo)
    result = await _run_loop(
        stream=stream,
        runner=runner,
        repo=repo,
        commit=fake_commit,
        session_id="paper-baseline-test",
        report_interval_seconds=0,  # emitir en el primer tick
        report_dir=report_dir,
        state_path=state_path,
        initial_equity=1000.0,
        deadline=asyncio.get_running_loop().time() + 1,
    )

    assert result.startswith("processed=")
    report_files = list(report_dir.glob("paper-*.md"))
    assert len(report_files) == 1
    text = report_files[0].read_text(encoding="utf-8")
    assert "# Paper Trading Periodic Report" in text
    assert state_path.exists()
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `uv run pytest tests/test_cli_paper_runner.py::test_run_loop_emits_report_after_interval -q`
Expected: FAIL (no existe `_run_loop`).

- [ ] **Step 3: Implementar `_run_loop` y refactorizar `_run`**

Reemplazar `src/interfaces/cli/paper_runner.py` por:

```python
from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from application.ports.paper_trading import PaperTradeEventRepository
from application.services.paper_runner import (
    PaperRunner,
    PaperRunnerConfig,
    PaperRunSummary,
    UnsafePaperModeError,
    summarize_events,
    write_certification_state,
    write_periodic_report,
)
from domain.market.candle import Timeframe
from domain.market.stream import KlineUpdate
from domain.risk.config import RiskConfig
from infrastructure.bybit.ws import BybitWebSocketClient
from infrastructure.database.repositories import SqlAlchemyPaperTradeEventRepository
from infrastructure.database.session import build_session_factory, create_engine
from settings import Settings

RunFn = Callable[[Settings, list[str], Timeframe, int | None], Coroutine[Any, Any, str]]
SECONDS_PER_DAY = 24 * 60 * 60


async def _run_loop(
    *,
    stream: Any,
    runner: PaperRunner,
    repo: PaperTradeEventRepository,
    commit: Callable[[], Awaitable[None]],
    session_id: str,
    report_interval_seconds: int,
    report_dir: Path,
    state_path: Path,
    initial_equity: float,
    deadline: float | None,
) -> str:
    loop = asyncio.get_running_loop()
    last_report_time = loop.time()
    last_summary: PaperRunSummary | None = None
    processed = 0
    while deadline is None or loop.time() < deadline:
        event = await stream.recv()
        if not isinstance(event, KlineUpdate):
            continue
        paper_event = await runner.handle_kline(event)
        if paper_event is not None:
            processed += 1
            await commit()
        now = loop.time()
        if now - last_report_time >= report_interval_seconds:
            try:
                events = await repo.list_session(session_id)
                summary = summarize_events(
                    events, previous=last_summary, initial_equity=initial_equity
                )
                ts = summary.latest_timestamp_ms or 0
                name = f"paper-{datetime.fromtimestamp(ts / 1000, tz=timezone.utc):%Y%m%d-%H%M%S}.md"
                write_periodic_report(summary, report_dir / name)
                write_certification_state(summary, state_path)
                last_summary = summary
                last_report_time = now
            except OSError as exc:
                print(f"[paper-runner] WARN: report write failed: {exc}")
    return f"processed={processed}"


async def _run(
    settings: Settings, symbols: list[str], timeframe: Timeframe, seconds: int | None
) -> str:
    engine = create_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    session = session_factory()
    stream = BybitWebSocketClient(url=settings.bybit_ws_url)
    try:
        repo = SqlAlchemyPaperTradeEventRepository(session)
        config = PaperRunnerConfig(
            trading_mode=settings.trading_mode,
            live_trading_enabled=settings.live_trading_enabled,
            symbols=tuple(symbols),
            timeframe=timeframe.label,
            session_id=f"paper-baseline-{timeframe.label}-{symbols[0].lower()}",
            decision_source=settings.paper_decision_source,
            report_interval_seconds=settings.paper_report_interval_hours * 60 * 60,
            max_runtime_seconds=seconds,
        )
        runner = PaperRunner(config=config, event_repo=repo)
        await stream.connect()
        for symbol in symbols:
            await stream.subscribe_kline(symbol, timeframe)
        deadline = None
        if seconds is not None:
            deadline = asyncio.get_running_loop().time() + seconds
        return await _run_loop(
            stream=stream,
            runner=runner,
            repo=repo,
            commit=session.commit,
            session_id=config.session_id,
            report_interval_seconds=config.report_interval_seconds,
            report_dir=Path(settings.paper_report_dir),
            state_path=Path(settings.paper_certification_state_path),
            initial_equity=RiskConfig().capital,
            deadline=deadline,
        )
    finally:
        await session.close()
        await engine.dispose()
        await stream.close()


def run_paper_runner(settings: Settings, argv: list[str] | None = None, run: RunFn = _run) -> int:
    parser = argparse.ArgumentParser(prog="paper-runner")
    parser.add_argument("--symbols", nargs="+", default=None)
    parser.add_argument("--timeframe", default=None)
    parser.add_argument("--seconds", type=int, default=None)
    args = parser.parse_args(argv)
    try:
        timeframe = Timeframe.from_label(args.timeframe or settings.paper_timeframe)
        symbols = args.symbols or list(settings.paper_symbols)
        max_runtime_seconds = args.seconds
        if max_runtime_seconds is None:
            max_runtime_seconds = settings.paper_max_runtime_days * SECONDS_PER_DAY
        result = asyncio.run(run(settings, symbols, timeframe, max_runtime_seconds))
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2
    except UnsafePaperModeError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(f"[paper-runner] {result}")
    return 0


def paper_runner(argv: list[str] | None) -> int:
    return run_paper_runner(Settings(), argv)
```

- [ ] **Step 4: Ejecutar todos los tests del CLI**

Run: `uv run pytest tests/test_cli_paper_runner.py -q`
Expected: PASS (los 3 tests existentes + el nuevo).

- [ ] **Step 5: Evidencia**

Run: `bash harness/scripts/evidence.sh 16 paper-runner-cli-reports-tests -- uv run pytest tests/test_cli_paper_runner.py -q`
Expected: exit 0.

---

### Task 4: Compose con bind-mounts de reportes

**Files:**
- Modify: `compose.yaml`
- Test: `docker compose config` (dry-run)

**Interfaces:**
- Consumes: servicio `paper-runner` existente (Task 3 del plan de runner previo).
- Produces: bind-mounts `./reports:/app/reports:rw` y `./certification:/app/certification:rw` en `paper-runner`.

- [ ] **Step 1: Añadir volúmenes al servicio `paper-runner`**

En `compose.yaml`, dentro de `paper-runner:` tras `depends_on`:

```yaml
    volumes:
      - ./reports:/app/reports:rw
      - ./certification:/app/certification:rw
```

- [ ] **Step 2: Alinear defaults de Settings con el layout del contenedor**

`paper_report_dir` ya es `reports/paper` → dentro del contenedor queda `/app/reports/paper`. `paper_certification_state_path` default es `docs/phases/16/certification-state.json`, pero en el contenedor se debe escribir a `/app/certification/certification-state.json`. Añadir a `compose.yaml` `environment` del servicio:

```yaml
      PAPER_REPORT_DIR: reports/paper
      PAPER_CERTIFICATION_STATE_PATH: /app/certification/certification-state.json
```

- [ ] **Step 3: Validar compose (dry-run, pre-gate)**

Run: `docker compose config`
Expected: exit 0 y muestra los dos bind-mounts y las dos env vars.

- [ ] **Step 4: Evidencia**

Run: `bash harness/scripts/evidence.sh 16 compose-config-reports -- docker compose config`
Expected: exit 0.

---

### Task 5: Verificación local completa, lint, typing, coverage

**Files:**
- Modify: `docs/phases/phase-16-report.md` (sección Baseline Runner Readiness → reports)
- Modify: `docs/uat/phase-16-uat.md`
- Test: suite enfocada + lint + typing + coverage

**Interfaces:**
- Consumes: Tasks 1–4.

- [ ] **Step 1: Suite enfocada**

Run: `bash harness/scripts/evidence.sh 16 paper-runner-reports-focused-tests -- uv run pytest tests/test_paper_runner.py tests/test_cli_paper_runner.py tests/test_settings.py tests/integration/test_paper_trading_repository.py harness/tests/test_paper_certification.py -q`
Expected: exit 0.

- [ ] **Step 2: Lint**

Run: `bash harness/scripts/evidence.sh 16 paper-runner-reports-lint -- bash -c 'uv run ruff check . && uv run ruff format --check .'`
Expected: exit 0.

- [ ] **Step 3: Typing**

Run: `bash harness/scripts/evidence.sh 16 paper-runner-reports-typing -- uv run mypy src/application/ports/paper_trading.py src/application/services/paper_runner.py src/interfaces/cli/paper_runner.py src/settings.py`
Expected: exit 0.

- [ ] **Step 4: Coverage**

Run: `bash harness/scripts/evidence.sh 16 paper-runner-reports-coverage -- uv run pytest tests/test_paper_runner.py tests/test_cli_paper_runner.py tests/test_settings.py --cov=src --cov-branch --cov-report=json:docs/phases/16/evidence/coverage-reports.json --cov-fail-under=90 -q`
Expected: exit 0.

- [ ] **Step 5: Actualizar `docs/phases/phase-16-report.md`**

Añadir al final de la sección `## Baseline Runner Readiness`:

```markdown
## Periodic Reports (2026-09-01)

El runner emite reportes periódicos a `reports/paper/paper-<UTC>.md` cada 24h desde el arranque
(decisiones, fills, fees, slippage, equity, PnL absoluto/%, delta vs reporte anterior) y actualiza
`certification/certification-state.json`. La emisión se probó en local; el despliegue real en
`lenovosrv` requiere rebuild de la imagen y `docker compose up -d paper-runner`.
```

- [ ] **Step 6: Actualizar `docs/uat/phase-16-uat.md`**

Añadir fila a la tabla manual:

```markdown
| 4 | Tras rebuild: `docker compose logs --tail=100 paper-runner` y `ls reports/paper/` | Logs muestran klines procesados; existe al menos un `paper-*.md` tras el primer intervalo. |
```

- [ ] **Step 7: Gate check honesto**

Run: `bash harness/scripts/evidence.sh 16 gate-check-reports -- python3 harness/scripts/gate_check.py --phase 16`
Expected: exit 1 (scope-complete sigue bloqueado por 30 días/200 trades/2 regímenes/reportes reales); `lint-green` y `typing-green` PASS.

- [ ] **Step 8: No marcar umbrales reales done**

No marcar `certificacion-30-dias`, `certificacion-200-trades`, `certificacion-2-regimenes` ni `informes-periodicos`. Este último vuelve a `done` SOLO cuando existan reportes reales emitidos por el runner desplegado (evidencia del server).

---

## Execution Notes

- La implementación NO incluye APPLY al server: el rebuild + `docker compose up -d paper-runner` en `lenovosrv` requieren autorización explícita posterior (cambio de infraestructura ya aprobado vía DP-004, pero el redeplegado tras cambios de código se pide por separado).
- Si algún test revela que el runner necesitaría importar APIs privadas de Bybit, rechazar ese camino: la ejecución paper debe seguir siendo simulación local.
- `_run_loop` recibe `stream: Any` para mantener la firma simple; el tipo concreto real es `BybitWebSocketClient` y los fakes en tests solo implementan `recv` (y opcionalmente `connect/subscribe_kline/close`).
- El bucle emite reporte incluso con `report_interval_seconds=0` en el primer tick (comportamiento usado en tests; en producción es 86400).

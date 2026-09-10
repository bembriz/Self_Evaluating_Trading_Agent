# Phase 16 Real Paper Baseline Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and prepare a 7-day real-time paper trading baseline runner for `lenovosrv`, using real Bybit Production market data and simulated local paper execution.

**Architecture:** Add a new application orchestration service that consumes confirmed Bybit kline events, turns them into `EmaRsiBaseline` decisions, sends them through the existing `PaperEngine`, and persists auditable paper events. Keep the existing domain/risk/paper-engine behavior unchanged; add persistence, CLI, reporting, and Docker Compose wiring around it.

**Tech Stack:** Python 3.12, asyncio, SQLAlchemy 2 async, Alembic, PostgreSQL/pgvector, existing Bybit WebSocket adapter, existing `PaperEngine`, Docker Compose.

## Global Constraints

- Use `decision_source = baseline` and `EmaRsiBaseline` for the first 7 days.
- Initial runtime values: `symbol = ETHUSDT`, `timeframe = 15m`, `restart_policy = unless-stopped`, `host = lenovosrv`.
- Startup must reject unsafe config: `TRADING_MODE=paper` and `LIVE_TRADING_ENABLED=false` are required.
- No Bybit LIVE order placement and no Bybit Testnet orders in this runner.
- The runner must not import or call `infrastructure.bybit.trade_client`.
- No LLM calls during the first 7-day baseline runner.
- No artificial trades and no time compression to satisfy Phase 16 thresholds.
- A Gemini paper run after day 7 must use a new strategy version/hash and is out of scope for this plan.
- Docker/server APPLY requires an infra/dependency proposal and explicit user approval before `docker build`, `docker compose up`, remote service creation, or bind-mount creation on `lenovosrv`.
- Do not commit/push/merge/tag without explicit user authorization.
- Gate-relevant commands must be captured through `bash harness/scripts/evidence.sh 16 <name> -- <command>`.

---

## File Structure

- Create `src/application/ports/paper_trading.py`: Protocols and dataclasses for paper run persistence.
- Create `src/application/services/paper_runner.py`: real-time baseline runner orchestration, safe-mode validation, bounded runtime loop, report snapshots.
- Modify `src/infrastructure/database/models.py`: add ORM table for paper events.
- Modify `src/infrastructure/database/repositories.py`: add SQLAlchemy repository for paper events.
- Create `migrations/versions/0008_paper_trading_events.py`: DB migration for paper events.
- Create `src/interfaces/cli/paper_runner.py`: CLI composition root for local/container execution.
- Modify `src/main.py`: add `paper-runner` subcommand.
- Modify `src/settings.py`: add paper runtime settings.
- Modify `config/paper.yaml`: safe paper profile for baseline runtime.
- Modify `.env.example`: document non-secret paper variables.
- Modify `compose.yaml`: add `paper-runner` service behind infra gate.
- Modify `Dockerfile` only if current image cannot run `python -m main paper-runner` safely.
- Create `tests/test_paper_runner.py`: service unit tests.
- Create `tests/test_cli_paper_runner.py`: CLI tests.
- Create `tests/integration/test_paper_trading_repository.py`: repository integration tests.
- Create/update `docs/phases/16/DP-004-paper-runner-container-deployment.md`: infra proposal for Docker/server deployment.
- Update `docs/phases/phase-16-report.md`, `docs/uat/phase-16-uat.md`, and evidence logs after implementation.

---

### Task 1: Paper Event Persistence Contract And Migration

**Files:**
- Create: `src/application/ports/paper_trading.py`
- Modify: `src/infrastructure/database/models.py`
- Modify: `src/infrastructure/database/repositories.py`
- Create: `migrations/versions/0008_paper_trading_events.py`
- Test: `tests/integration/test_paper_trading_repository.py`

**Interfaces:**
- Consumes: existing `infrastructure.database.session.create_engine`, `build_session_factory`, and Alembic test patterns.
- Produces:
  - `PaperTradeEvent` dataclass with fields: `session_id: str`, `strategy_version: str`, `strategy_hash: str`, `decision_source: str`, `symbol: str`, `timeframe: str`, `timestamp_ms: int`, `action: str`, `filled: bool`, `risk_reason: str`, `exit_reason: str`, `exec_price: float | None`, `quantity: float | None`, `fee: float`, `slippage_cost: float`, `equity: float`, `kill_switch_active: bool`.
  - `PaperTradeEventRepository` Protocol with `add(event: PaperTradeEvent) -> Awaitable[None]` and `list_session(session_id: str) -> Awaitable[list[PaperTradeEvent]]`.
  - `SqlAlchemyPaperTradeEventRepository` implementation.

- [ ] **Step 1: Write failing repository integration test**

Create `tests/integration/test_paper_trading_repository.py`:

```python
from application.ports.paper_trading import PaperTradeEvent
from infrastructure.database.repositories import SqlAlchemyPaperTradeEventRepository


async def test_paper_trade_event_repository_roundtrip(db_session) -> None:
    repo = SqlAlchemyPaperTradeEventRepository(db_session)
    event = PaperTradeEvent(
        session_id="paper-baseline-20260901",
        strategy_version="ema-rsi-baseline-v1",
        strategy_hash="abc123",
        decision_source="baseline",
        symbol="ETHUSDT",
        timeframe="15m",
        timestamp_ms=1_725_000_000_000,
        action="BUY",
        filled=True,
        risk_reason="",
        exit_reason="",
        exec_price=2500.5,
        quantity=0.01,
        fee=0.025,
        slippage_cost=0.005,
        equity=999.97,
        kill_switch_active=False,
    )

    await repo.add(event)
    await db_session.commit()

    rows = await repo.list_session("paper-baseline-20260901")
    assert rows == [event]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_paper_trading_repository.py -q`

Expected: FAIL because `application.ports.paper_trading` or repository/model does not exist.

- [ ] **Step 3: Create persistence contract**

Create `src/application/ports/paper_trading.py`:

```python
from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PaperTradeEvent:
    session_id: str
    strategy_version: str
    strategy_hash: str
    decision_source: str
    symbol: str
    timeframe: str
    timestamp_ms: int
    action: str
    filled: bool
    risk_reason: str
    exit_reason: str
    exec_price: float | None
    quantity: float | None
    fee: float
    slippage_cost: float
    equity: float
    kill_switch_active: bool


class PaperTradeEventRepository(Protocol):
    def add(self, event: PaperTradeEvent) -> Awaitable[None]: ...

    def list_session(self, session_id: str) -> Awaitable[list[PaperTradeEvent]]: ...
```

- [ ] **Step 4: Add ORM model**

Modify `src/infrastructure/database/models.py` by importing `Boolean` and adding:

```python
class PaperTradeEventRecord(Base):
    """Auditable event from real-time paper trading execution."""

    __tablename__ = "paper_trade_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(96), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    decision_source: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    timestamp_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(8), nullable=False)
    filled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    risk_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    exit_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    exec_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    fee: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    slippage_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    equity: Mapped[float] = mapped_column(Float, nullable=False)
    kill_switch_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("ix_paper_trade_events_session_ts", "session_id", "timestamp_ms"),
        Index("ix_paper_trade_events_symbol_tf_ts", "symbol", "timeframe", "timestamp_ms"),
    )
```

- [ ] **Step 5: Add SQLAlchemy repository**

Modify `src/infrastructure/database/repositories.py` imports and add:

```python
from application.ports.paper_trading import PaperTradeEvent
from infrastructure.database.models import PaperTradeEventRecord
```

Then add class:

```python
class SqlAlchemyPaperTradeEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: PaperTradeEvent) -> None:
        self._session.add(
            PaperTradeEventRecord(
                session_id=event.session_id,
                strategy_version=event.strategy_version,
                strategy_hash=event.strategy_hash,
                decision_source=event.decision_source,
                symbol=event.symbol,
                timeframe=event.timeframe,
                timestamp_ms=event.timestamp_ms,
                action=event.action,
                filled=event.filled,
                risk_reason=event.risk_reason,
                exit_reason=event.exit_reason,
                exec_price=event.exec_price,
                quantity=event.quantity,
                fee=event.fee,
                slippage_cost=event.slippage_cost,
                equity=event.equity,
                kill_switch_active=event.kill_switch_active,
            )
        )
        await self._session.flush()

    async def list_session(self, session_id: str) -> list[PaperTradeEvent]:
        rows = (
            await self._session.scalars(
                select(PaperTradeEventRecord)
                .where(PaperTradeEventRecord.session_id == session_id)
                .order_by(PaperTradeEventRecord.timestamp_ms, PaperTradeEventRecord.id)
            )
        ).all()
        return [self._to_domain(row) for row in rows]

    @staticmethod
    def _to_domain(row: PaperTradeEventRecord) -> PaperTradeEvent:
        return PaperTradeEvent(
            session_id=row.session_id,
            strategy_version=row.strategy_version,
            strategy_hash=row.strategy_hash,
            decision_source=row.decision_source,
            symbol=row.symbol,
            timeframe=row.timeframe,
            timestamp_ms=row.timestamp_ms,
            action=row.action,
            filled=row.filled,
            risk_reason=row.risk_reason,
            exit_reason=row.exit_reason,
            exec_price=row.exec_price,
            quantity=row.quantity,
            fee=row.fee,
            slippage_cost=row.slippage_cost,
            equity=row.equity,
            kill_switch_active=row.kill_switch_active,
        )
```

- [ ] **Step 6: Add Alembic migration**

Create `migrations/versions/0008_paper_trading_events.py` with revision `0008_paper_trading_events`, down_revision equal to the current latest migration, and table/index definitions matching the ORM model. Use `op.create_table`, `op.create_index`, `op.drop_index`, and `op.drop_table`.

- [ ] **Step 7: Run focused integration test**

Run: `uv run pytest tests/integration/test_paper_trading_repository.py -q`

Expected: PASS.

- [ ] **Step 8: Run migration roundtrip test**

Run: `uv run pytest tests/integration/test_alembic.py -q`

Expected: PASS.

- [ ] **Step 9: Record evidence**

Run: `bash harness/scripts/evidence.sh 16 paper-event-repository-tests -- uv run pytest tests/integration/test_paper_trading_repository.py tests/integration/test_alembic.py -q`

Expected: exit 0.

---

### Task 2: Baseline Paper Runner Service

**Files:**
- Create: `src/application/services/paper_runner.py`
- Test: `tests/test_paper_runner.py`

**Interfaces:**
- Consumes: `PaperTradeEvent`, `PaperTradeEventRepository`, `PaperEngine`, `RiskConfig`, `EmaRsiBaseline`, `TradingDecision`, `KlineUpdate`, `Timeframe`.
- Produces:
  - `PaperRunnerConfig` dataclass.
  - `UnsafePaperModeError` exception.
  - `PaperRunner` class with `handle_kline(kline: KlineUpdate) -> Awaitable[PaperTradeEvent | None]` and `run_once() -> Awaitable[None]`.
  - `strategy_hash(strategy_version: str, decision_source: str) -> str`.

- [ ] **Step 1: Write failing safety test**

Create `tests/test_paper_runner.py`:

```python
import pytest

from application.services.paper_runner import PaperRunnerConfig, UnsafePaperModeError


def test_paper_runner_config_rejects_live_enabled() -> None:
    with pytest.raises(UnsafePaperModeError, match="LIVE_TRADING_ENABLED"):
        PaperRunnerConfig(
            trading_mode="paper",
            live_trading_enabled=True,
            symbols=("ETHUSDT",),
            timeframe="15m",
            session_id="paper-baseline-test",
        ).validate_safe()


def test_paper_runner_config_rejects_non_paper_mode() -> None:
    with pytest.raises(UnsafePaperModeError, match="TRADING_MODE"):
        PaperRunnerConfig(
            trading_mode="backtest",
            live_trading_enabled=False,
            symbols=("ETHUSDT",),
            timeframe="15m",
            session_id="paper-baseline-test",
        ).validate_safe()
```

- [ ] **Step 2: Run safety tests red**

Run: `uv run pytest tests/test_paper_runner.py::test_paper_runner_config_rejects_live_enabled tests/test_paper_runner.py::test_paper_runner_config_rejects_non_paper_mode -q`

Expected: FAIL because module/classes do not exist.

- [ ] **Step 3: Implement config and safety validation**

Create `src/application/services/paper_runner.py` with:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass


class UnsafePaperModeError(RuntimeError):
    pass


def strategy_hash(strategy_version: str, decision_source: str) -> str:
    payload = f"{decision_source}:{strategy_version}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class PaperRunnerConfig:
    trading_mode: str
    live_trading_enabled: bool
    symbols: tuple[str, ...]
    timeframe: str
    session_id: str
    decision_source: str = "baseline"
    report_interval_seconds: int = 24 * 60 * 60
    max_runtime_seconds: int | None = None

    def validate_safe(self) -> None:
        if self.trading_mode != "paper":
            raise UnsafePaperModeError("TRADING_MODE must be paper for paper-runner")
        if self.live_trading_enabled:
            raise UnsafePaperModeError("LIVE_TRADING_ENABLED must be false for paper-runner")
        if self.decision_source != "baseline":
            raise UnsafePaperModeError("baseline paper-runner only supports decision_source=baseline")
        if not self.symbols:
            raise UnsafePaperModeError("at least one symbol is required")
```

- [ ] **Step 4: Run safety tests green**

Run: `uv run pytest tests/test_paper_runner.py -q`

Expected: PASS for current tests.

- [ ] **Step 5: Write failing kline orchestration test**

Append to `tests/test_paper_runner.py`:

```python
from application.ports.paper_trading import PaperTradeEvent
from application.services.paper_runner import PaperRunner
from domain.market.candle import Timeframe
from domain.market.stream import KlineUpdate


class FakePaperTradeRepo:
    def __init__(self) -> None:
        self.events: list[PaperTradeEvent] = []

    async def add(self, event: PaperTradeEvent) -> None:
        self.events.append(event)

    async def list_session(self, session_id: str) -> list[PaperTradeEvent]:
        return [event for event in self.events if event.session_id == session_id]


async def test_runner_ignores_unconfirmed_kline() -> None:
    repo = FakePaperTradeRepo()
    runner = PaperRunner(config=_safe_config(), event_repo=repo)
    kline = KlineUpdate("ETHUSDT", Timeframe.M15, 1_000, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, False)

    event = await runner.handle_kline(kline)

    assert event is None
    assert repo.events == []


async def test_runner_persists_event_for_confirmed_kline() -> None:
    repo = FakePaperTradeRepo()
    runner = PaperRunner(config=_safe_config(), event_repo=repo)
    kline = KlineUpdate("ETHUSDT", Timeframe.M15, 1_000, 100.0, 101.0, 99.0, 100.5, 10.0, 1005.0, True)

    event = await runner.handle_kline(kline)

    assert event is not None
    assert repo.events == [event]
    assert event.session_id == "paper-baseline-test"
    assert event.decision_source == "baseline"
    assert event.symbol == "ETHUSDT"
    assert event.timeframe == "15m"
    assert event.timestamp_ms == 1_000
    assert event.action in {"BUY", "SELL", "HOLD"}
    assert event.equity > 0.0
```

Also add helper:

```python
def _safe_config() -> PaperRunnerConfig:
    return PaperRunnerConfig(
        trading_mode="paper",
        live_trading_enabled=False,
        symbols=("ETHUSDT",),
        timeframe="15m",
        session_id="paper-baseline-test",
    )
```

- [ ] **Step 6: Run kline tests red**

Run: `uv run pytest tests/test_paper_runner.py -q`

Expected: FAIL because `PaperRunner` is not implemented.

- [ ] **Step 7: Implement minimal `PaperRunner.handle_kline`**

Append to `src/application/services/paper_runner.py`:

```python
from application.ports.paper_trading import PaperTradeEvent, PaperTradeEventRepository
from application.services.paper_engine import PaperEngine
from domain.market.stream import KlineUpdate
from domain.risk.config import RiskConfig
from domain.trading.decision import TradingDecision
from domain.trading.signal import Intensity
from domain.trading.strategy import EmaRsiBaseline


class PaperRunner:
    def __init__(
        self,
        *,
        config: PaperRunnerConfig,
        event_repo: PaperTradeEventRepository,
        paper_engine: PaperEngine | None = None,
        strategy: EmaRsiBaseline | None = None,
    ) -> None:
        config.validate_safe()
        self._config = config
        self._repo = event_repo
        self._strategy = strategy or EmaRsiBaseline()
        self._engine = paper_engine or PaperEngine(config=RiskConfig())
        self._strategy_hash = strategy_hash(self._strategy.version, config.decision_source)

    async def handle_kline(self, kline: KlineUpdate) -> PaperTradeEvent | None:
        candle = kline.to_candle()
        if candle is None:
            return None
        signal = self._strategy.on_candle(candle)
        decision = TradingDecision(
            timestamp_ms=candle.timestamp_ms,
            action=signal.action,
            confidence=1.0,
            intensity=Intensity.MEDIUM,
            rationale_summary=signal.reason,
        )
        paper_event = self._engine.on_price(
            decision=decision,
            price=candle.close,
            atr=None,
            timestamp_ms=candle.timestamp_ms,
        )
        fill = paper_event.fill
        event = PaperTradeEvent(
            session_id=self._config.session_id,
            strategy_version=self._strategy.version,
            strategy_hash=self._strategy_hash,
            decision_source=self._config.decision_source,
            symbol=kline.symbol,
            timeframe=kline.interval.label,
            timestamp_ms=candle.timestamp_ms,
            action=paper_event.action.value,
            filled=paper_event.filled,
            risk_reason=paper_event.risk_reason,
            exit_reason=paper_event.exit_reason,
            exec_price=fill.exec_price if fill is not None else None,
            quantity=fill.quantity if fill is not None else None,
            fee=fill.fee if fill is not None else 0.0,
            slippage_cost=fill.slippage_cost if fill is not None else 0.0,
            equity=self._engine.mark_to_market(price=candle.close),
            kill_switch_active=self._engine.kill_switch_state.active,
        )
        await self._repo.add(event)
        return event
```

- [ ] **Step 8: Run service tests green**

Run: `uv run pytest tests/test_paper_runner.py -q`

Expected: PASS.

- [ ] **Step 9: Record evidence**

Run: `bash harness/scripts/evidence.sh 16 paper-runner-service-tests -- uv run pytest tests/test_paper_runner.py -q`

Expected: exit 0.

---

### Task 3: Real-Time CLI Composition And Safe Runtime Config

**Files:**
- Create: `src/interfaces/cli/paper_runner.py`
- Modify: `src/main.py`
- Modify: `src/settings.py`
- Modify: `config/paper.yaml`
- Modify: `.env.example`
- Test: `tests/test_cli_paper_runner.py`
- Test: `tests/test_main.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: `PaperRunnerConfig`, `PaperRunner`, `SqlAlchemyPaperTradeEventRepository`, `BybitWebSocketClient`, `KlineUpdate`, `WebSocketDisconnected`, `Timeframe`.
- Produces:
  - `paper_runner(argv: list[str] | None) -> int`.
  - `run_paper_runner(..., argv: list[str] | None = None) -> int` for injection-friendly tests.

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli_paper_runner.py`:

```python
from interfaces.cli.paper_runner import paper_runner


def test_paper_runner_help_exits_zero() -> None:
    try:
        paper_runner(["--help"])
    except SystemExit as exc:
        assert exc.code == 0


def test_paper_runner_rejects_invalid_timeframe() -> None:
    code = paper_runner(["--timeframe", "5m", "--seconds", "1"])
    assert code == 2
```

Modify `tests/test_main.py` to include:

```python
def test_main_dispatches_paper_runner(monkeypatch) -> None:
    called: dict[str, list[str] | None] = {}

    def fake(argv: list[str] | None) -> int:
        called["argv"] = argv
        return 0

    from interfaces.cli import paper_runner as cli_paper_runner

    monkeypatch.setattr(cli_paper_runner, "paper_runner", fake)

    assert main(["paper-runner", "--seconds", "1"]) == 0
    assert called["argv"] == ["--seconds", "1"]
```

- [ ] **Step 2: Run CLI tests red**

Run: `uv run pytest tests/test_cli_paper_runner.py tests/test_main.py::test_main_dispatches_paper_runner -q`

Expected: FAIL because `interfaces.cli.paper_runner` and subcommand do not exist.

- [ ] **Step 3: Add settings fields**

Modify `src/settings.py` to add safe defaults:

```python
paper_decision_source: str = "baseline"
paper_symbols: list[str] = ["ETHUSDT"]
paper_timeframe: str = "15m"
paper_report_interval_hours: int = 24
paper_max_runtime_days: int = 7
```

Add/adjust tests in `tests/test_settings.py` so `Settings()` exposes these defaults and env overrides can set `TRADING_MODE=paper` and `LIVE_TRADING_ENABLED=false`.

- [ ] **Step 4: Implement CLI composition root**

Create `src/interfaces/cli/paper_runner.py`:

```python
from __future__ import annotations

import argparse
import asyncio

from application.services.paper_runner import PaperRunner, PaperRunnerConfig, UnsafePaperModeError
from domain.market.candle import Timeframe
from domain.market.stream import KlineUpdate
from infrastructure.bybit.ws import BybitWebSocketClient
from infrastructure.database.repositories import SqlAlchemyPaperTradeEventRepository
from infrastructure.database.session import build_session_factory, create_engine
from settings import Settings


async def _run(settings: Settings, symbols: list[str], timeframe: Timeframe, seconds: int | None) -> str:
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
        processed = 0
        while deadline is None or asyncio.get_running_loop().time() < deadline:
            event = await stream.recv()
            if isinstance(event, KlineUpdate):
                paper_event = await runner.handle_kline(event)
                if paper_event is not None:
                    processed += 1
                    await session.commit()
        return f"processed={processed}"
    finally:
        await session.close()
        await engine.dispose()
        await stream.close()


def paper_runner(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(prog="paper-runner")
    parser.add_argument("--symbols", nargs="+", default=None)
    parser.add_argument("--timeframe", default=None)
    parser.add_argument("--seconds", type=int, default=None)
    args = parser.parse_args(argv)
    settings = Settings()
    try:
        timeframe = Timeframe.from_label(args.timeframe or settings.paper_timeframe)
        symbols = args.symbols or list(settings.paper_symbols)
        result = asyncio.run(_run(settings, symbols, timeframe, args.seconds))
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2
    except UnsafePaperModeError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(f"[paper-runner] {result}")
    return 0
```

- [ ] **Step 5: Add main subcommand**

Modify `src/main.py`:

```python
from interfaces.cli import paper_runner as cli_paper_runner
...
sub.add_parser("paper-runner")
...
if args.command == "paper-runner":
    return cli_paper_runner.paper_runner(rest)
```

Update docstring to mention `paper-runner`.

- [ ] **Step 6: Update config docs**

Modify `config/paper.yaml`:

```yaml
environment: paper
trading_mode: paper
live_trading_enabled: false
paper_decision_source: baseline
paper_symbols:
  - ETHUSDT
paper_timeframe: 15m
paper_report_interval_hours: 24
paper_max_runtime_days: 7
```

Modify `.env.example` with names only:

```text
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
PAPER_DECISION_SOURCE=baseline
PAPER_SYMBOLS='["ETHUSDT"]'
PAPER_TIMEFRAME=15m
PAPER_REPORT_INTERVAL_HOURS=24
PAPER_MAX_RUNTIME_DAYS=7
```

- [ ] **Step 7: Run CLI/settings tests green**

Run: `uv run pytest tests/test_cli_paper_runner.py tests/test_main.py tests/test_settings.py -q`

Expected: PASS.

- [ ] **Step 8: Record evidence**

Run: `bash harness/scripts/evidence.sh 16 paper-runner-cli-tests -- uv run pytest tests/test_cli_paper_runner.py tests/test_main.py tests/test_settings.py -q`

Expected: exit 0.

---

### Task 4: Periodic Paper Reports And Certification State Update

**Files:**
- Modify: `src/application/services/paper_runner.py`
- Modify: `harness/scripts/paper_certification.py` if needed to consume generated state fields without weakening thresholds.
- Test: `tests/test_paper_runner.py`
- Test: `harness/tests/test_paper_certification.py`

**Interfaces:**
- Consumes: `PaperTradeEventRepository.list_session` and `PaperTradeEvent`.
- Produces:
  - `PaperRunSummary` dataclass.
  - `summarize_events(events: list[PaperTradeEvent]) -> PaperRunSummary`.
  - `write_periodic_report(summary: PaperRunSummary, report_path: Path) -> None`.
  - `write_certification_state(summary: PaperRunSummary, state_path: Path, previous: dict[str, Any] | None = None) -> None`.

- [ ] **Step 1: Write failing summary/report tests**

Append to `tests/test_paper_runner.py`:

```python
from pathlib import Path

from application.services.paper_runner import summarize_events, write_periodic_report


def test_summarize_events_counts_decisions_and_fills() -> None:
    events = [
        _paper_event(action="BUY", filled=True, fee=0.10, slippage_cost=0.02, equity=999.88),
        _paper_event(action="HOLD", filled=False, fee=0.0, slippage_cost=0.0, equity=999.88),
    ]

    summary = summarize_events(events)

    assert summary.decisions == {"BUY": 1, "SELL": 0, "HOLD": 1}
    assert summary.fills == 1
    assert summary.fees == 0.10
    assert summary.slippage == 0.02
    assert summary.latest_equity == 999.88


def test_write_periodic_report_contains_certification_progress(tmp_path: Path) -> None:
    summary = summarize_events([_paper_event(action="BUY", filled=True)])
    report = tmp_path / "paper-report.md"

    write_periodic_report(summary, report)

    text = report.read_text(encoding="utf-8")
    assert "# Paper Trading Periodic Report" in text
    assert "decision_source: baseline" in text
    assert "fills: 1" in text
```

Add helper:

```python
def _paper_event(
    *,
    action: str = "HOLD",
    filled: bool = False,
    fee: float = 0.0,
    slippage_cost: float = 0.0,
    equity: float = 1000.0,
) -> PaperTradeEvent:
    return PaperTradeEvent(
        session_id="paper-baseline-test",
        strategy_version="ema-rsi-baseline-v1",
        strategy_hash="abc123",
        decision_source="baseline",
        symbol="ETHUSDT",
        timeframe="15m",
        timestamp_ms=1_000,
        action=action,
        filled=filled,
        risk_reason="",
        exit_reason="",
        exec_price=100.0 if filled else None,
        quantity=0.1 if filled else None,
        fee=fee,
        slippage_cost=slippage_cost,
        equity=equity,
        kill_switch_active=False,
    )
```

- [ ] **Step 2: Run report tests red**

Run: `uv run pytest tests/test_paper_runner.py::test_summarize_events_counts_decisions_and_fills tests/test_paper_runner.py::test_write_periodic_report_contains_certification_progress -q`

Expected: FAIL because summary/report functions do not exist.

- [ ] **Step 3: Implement summary/report functions**

Add to `src/application/services/paper_runner.py`:

```python
from pathlib import Path
from typing import Any


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


def summarize_events(events: list[PaperTradeEvent]) -> PaperRunSummary:
    decisions = {"BUY": 0, "SELL": 0, "HOLD": 0}
    ordered = sorted(events, key=lambda event: event.timestamp_ms)
    for event in ordered:
        decisions[event.action] = decisions.get(event.action, 0) + 1
    first = ordered[0] if ordered else None
    last = ordered[-1] if ordered else None
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
        latest_equity=last.equity if last else 0.0,
        kill_switch_active=last.kill_switch_active if last else False,
    )


def write_periodic_report(summary: PaperRunSummary, report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
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
                f"latest_equity: {summary.latest_equity:.8f}",
                f"kill_switch_active: {summary.kill_switch_active}",
                "",
            ]
        ),
        encoding="utf-8",
    )
```

- [ ] **Step 4: Add certification state writer test**

Append to `tests/test_paper_runner.py`:

```python
import json

from application.services.paper_runner import write_certification_state


def test_write_certification_state_keeps_pending_thresholds_honest(tmp_path: Path) -> None:
    state_path = tmp_path / "certification-state.json"
    summary = summarize_events([_paper_event(action="BUY", filled=True)])

    write_certification_state(summary, state_path)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["strategy_hash"] == "abc123"
    assert state["active_strategy_hash"] == "abc123"
    assert state["trade_count"] == 1
    assert state["calendar_days"] == 1
    assert state["market_regimes"] == []
    assert state["periodic_reports"] == []
```

- [ ] **Step 5: Implement certification state writer**

Add to `src/application/services/paper_runner.py`:

```python
import json


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
            "periodic_reports": data.get("periodic_reports", []),
        }
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
```

- [ ] **Step 6: Run report/state tests green**

Run: `uv run pytest tests/test_paper_runner.py harness/tests/test_paper_certification.py -q`

Expected: PASS.

- [ ] **Step 7: Record evidence**

Run: `bash harness/scripts/evidence.sh 16 paper-runner-report-tests -- uv run pytest tests/test_paper_runner.py harness/tests/test_paper_certification.py -q`

Expected: exit 0.

---

### Task 5: Docker Compose Service And Infra Proposal

**Files:**
- Create: `docs/phases/16/DP-004-paper-runner-container-deployment.md`
- Modify: `compose.yaml`
- Modify: `Dockerfile` only if needed.
- Modify: `.dockerignore` only if needed.
- Test: `docker compose config` dry-run only before approval.

**Interfaces:**
- Consumes: `python -m main paper-runner` from Task 3.
- Produces: Compose service `paper-runner` using `restart: unless-stopped`, no public ports, no `.envrc` copied into image.

- [ ] **Step 1: Write infra proposal before any APPLY**

Create `docs/phases/16/DP-004-paper-runner-container-deployment.md` from `harness/templates/dependency-proposal.md` with these exact facts:

```markdown
# DP-004 — Paper Runner Container Deployment

## Necesidad

Run Phase 16 baseline paper trading for 7 calendar days on `lenovosrv` using Docker Compose with `restart: unless-stopped`.

## Cambios Solicitados

- Add Compose service `paper-runner`.
- Build/use the existing project image.
- Run `python -m main paper-runner --symbols ETHUSDT --timeframe 15m`.
- Keep `LIVE_TRADING_ENABLED=false`.
- Use existing `postgres`, `prometheus`, and `grafana` services.
- Deploy under `/srv/docker/self-evaluating-trading-agent/...` on `lenovosrv` during APPLY.

## Seguridad

- No `.envrc` copied into image.
- No LIVE trading.
- No Bybit private order client used.
- No public port exposure added.
- Secrets remain environment variables only.

## Pre-Gate Validation

- `docker compose config` only.
- No `docker build`, `docker pull`, `docker compose up`, remote bind mounts, or firewall changes before APPROVED.

## Rollback

- Stop service with `docker compose stop paper-runner`.
- Remove service definition in a reverting change.
- Preserve PostgreSQL volume and evidence artifacts unless user explicitly authorizes deletion.
```

- [ ] **Step 2: Modify Compose service**

Add to `compose.yaml`:

```yaml
  paper-runner:
    build: .
    command: ["python", "-m", "main", "paper-runner", "--symbols", "ETHUSDT", "--timeframe", "15m"]
    restart: unless-stopped
    environment:
      TRADING_MODE: paper
      LIVE_TRADING_ENABLED: "false"
      POSTGRES_HOST: postgres
      POSTGRES_PORT: "5432"
      POSTGRES_DB: ${POSTGRES_DB:-trading_agent}
      POSTGRES_USER: ${POSTGRES_USER:-trading}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-trading}
      PAPER_DECISION_SOURCE: baseline
      PAPER_TIMEFRAME: 15m
    depends_on:
      postgres:
        condition: service_healthy
```

Do not add `ports` to `paper-runner`.

- [ ] **Step 3: Validate Compose without APPLY**

Run: `docker compose config`

Expected: exit 0. This is allowed pre-gate because it is a dry-run configuration render.

- [ ] **Step 4: Record dry-run evidence**

Run: `bash harness/scripts/evidence.sh 16 compose-config-paper-runner -- docker compose config`

Expected: exit 0.

- [ ] **Step 5: Stop and request explicit user approval for APPLY**

Do not run `docker build`, `docker compose up`, SSH deployment, or create `/srv/docker/...` paths until the user approves DP-004 explicitly.

---

### Task 6: Local Verification, Phase Report, And UAT Update

**Files:**
- Modify: `docs/phases/phase-16-report.md`
- Modify: `docs/uat/phase-16-uat.md`
- Modify: `.superpowers/sdd/2026-09-01-phase-16-paper-trading-certification/progress.md` only if continuing SDD bookkeeping.

**Interfaces:**
- Consumes: all previous tasks and evidence paths.
- Produces: updated Phase 16 docs that say baseline runner is ready for infra APPLY but not yet certified.

- [ ] **Step 1: Run focused tests**

Run: `bash harness/scripts/evidence.sh 16 paper-runner-focused-tests -- uv run pytest tests/test_paper_runner.py tests/test_cli_paper_runner.py tests/integration/test_paper_trading_repository.py harness/tests/test_paper_certification.py -q`

Expected: exit 0.

- [ ] **Step 2: Run lint evidence**

Run: `bash harness/scripts/evidence.sh 16 lint -- bash -c 'uv run ruff check . && uv run ruff format --check .'`

Expected: exit 0 and creates/updates `docs/phases/16/evidence/lint.log`.

- [ ] **Step 3: Run typing evidence for touched code**

Run: `bash harness/scripts/evidence.sh 16 typing -- uv run mypy src/application/ports/paper_trading.py src/application/services/paper_runner.py src/interfaces/cli/paper_runner.py tests/test_paper_runner.py tests/test_cli_paper_runner.py`

Expected: exit 0 and creates/updates `docs/phases/16/evidence/typing.log`.

- [ ] **Step 4: Run coverage evidence**

Run: `bash harness/scripts/evidence.sh 16 unit-coverage -- uv run pytest tests/test_paper_runner.py tests/test_cli_paper_runner.py harness/tests/test_paper_certification.py --cov=src --cov=harness/scripts --cov-branch --cov-report=json:docs/phases/16/evidence/coverage.json --cov-fail-under=90 -q`

Expected: exit 0.

- [ ] **Step 5: Update phase report**

Modify `docs/phases/phase-16-report.md` to add a section stating:

```markdown
## Baseline Runner Readiness

The 7-day baseline paper runner is implemented and locally verified. It is not yet deployed to `lenovosrv`; deployment remains blocked until DP-004 is explicitly approved. Phase 16 certification remains PENDING until real calendar days, real paper fills, market regimes, and periodic reports exist.
```

- [ ] **Step 6: Update UAT**

Modify `docs/uat/phase-16-uat.md` to include manual checks:

```markdown
| Step | Command | Expected |
|---|---|---|
| 1 | `docker compose config` | Shows `paper-runner` with `restart: unless-stopped`, no `ports`, `TRADING_MODE=paper`, `LIVE_TRADING_ENABLED=false`. |
| 2 | After DP-004 approval only: `docker compose up -d postgres paper-runner` | Service starts and remains running. |
| 3 | `docker compose logs --tail=100 paper-runner` | Logs show Bybit kline processing and paper events, no LIVE order placement. |
```

- [ ] **Step 7: Run final gate check**

Run: `bash harness/scripts/evidence.sh 16 gate-check-paper-runner -- python3 harness/scripts/gate_check.py --phase 16`

Expected: exit 1 because `scope-complete` remains blocked by real 30-day/200-trade/2-regime/report thresholds. `lint-green` and `typing-green` must PASS.

- [ ] **Step 8: Do not mark real thresholds done**

Do not mark any of these done:

```text
certificacion-30-dias
certificacion-200-trades
certificacion-2-regimenes
informes-periodicos
```

Only mark implementation/readiness deliverables if they exist in the ledger and have real evidence.

---

## Execution Notes

- This plan intentionally stops before server APPLY unless the user explicitly approves DP-004.
- After DP-004 approval, deployment commands must be run through `harness/scripts/evidence.sh` and must not expose public ports or copy secrets into images.
- If any test uncovers that the runner needs to call private Bybit APIs, reject that path. Paper execution must remain local simulation.
- If the baseline runner produces zero fills during 7 days, that is valid operational evidence but may not satisfy the 200-trade threshold.
- The day-8 Gemini activation needs a separate spec/plan or a separate follow-up section after baseline stabilization evidence exists.

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from application.ports.market_stream import WebSocketDisconnected
from application.ports.paper_trading import PaperTradeEventRepository
from application.services.connection_supervisor import ConnectionSupervisor, SupervisorConfig
from application.services.paper_runner import (
    PaperRunner,
    PaperRunnerConfig,
    PaperRunSummary,
    UnsafePaperModeError,
    load_certification_state,
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
from infrastructure.observability.metrics import SetaMetrics
from infrastructure.observability.server import start_metrics_server
from settings import Settings

RunFn = Callable[[Settings, list[str], Timeframe, int | None], Coroutine[Any, Any, str]]
SECONDS_PER_DAY = 24 * 60 * 60


def _default_session_id(timeframe: str, first_symbol: str) -> str:
    return f"paper-baseline-{timeframe}-{first_symbol.lower()}"


def resolve_session_id(settings: Settings, timeframe: Timeframe, first_symbol: str) -> str:
    if settings.paper_session_id:
        return settings.paper_session_id
    return _default_session_id(timeframe.label, first_symbol)


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
    recover: Callable[[], Awaitable[None]] | None = None,
    metrics: SetaMetrics | None = None,
    stale_timeout_seconds: float = 10.0,
) -> str:
    loop = asyncio.get_running_loop()
    last_report_time = loop.time()
    last_summary: PaperRunSummary | None = None
    processed = 0
    while deadline is None or loop.time() < deadline:
        try:
            if stale_timeout_seconds > 0:
                event = await asyncio.wait_for(stream.recv(), timeout=stale_timeout_seconds)
            else:
                event = await stream.recv()
        except TimeoutError:
            if metrics is not None:
                metrics.inc_stale()
                metrics.inc_reconnect()
                metrics.set_connected(False)
            if recover is None:
                raise
            await recover()
            if metrics is not None:
                metrics.set_connected(True)
            continue
        except WebSocketDisconnected:
            if metrics is not None:
                metrics.inc_error("ws")
                metrics.inc_reconnect()
                metrics.set_connected(False)
            if recover is None:
                raise
            await recover()
            if metrics is not None:
                metrics.set_connected(True)
            continue
        if not isinstance(event, KlineUpdate):
            continue
        paper_event = await runner.handle_kline(event)
        if paper_event is not None:
            processed += 1
            if metrics is not None:
                metrics.inc_candle()
                metrics.set_atr_ready(runner.atr_ready)
            await commit()
        now = loop.time()
        if now - last_report_time >= report_interval_seconds:
            try:
                events = await repo.list_session(session_id)
                summary = summarize_events(
                    events, previous=last_summary, initial_equity=initial_equity
                )
                ts = summary.latest_timestamp_ms or 0
                name = f"paper-{datetime.fromtimestamp(ts / 1000, tz=UTC):%Y%m%d-%H%M%S}.md"
                report_path = report_dir / name
                write_periodic_report(
                    summary,
                    report_path,
                    regime_evidence=runner.regime_evidence(),
                    rejected_regime_candidates=runner.rejected_regime_candidates,
                )
                write_certification_state(
                    summary,
                    state_path,
                    previous=load_certification_state(state_path),
                    regime_evidence=runner.regime_evidence(),
                    report_path=report_path,
                )
                last_summary = summary
                last_report_time = now
            except (OSError, ValueError) as exc:
                print(f"[paper-runner] WARN: report write failed: {exc}")
    return f"processed={processed}"


async def _run(
    settings: Settings, symbols: list[str], timeframe: Timeframe, seconds: int | None
) -> str:
    engine = create_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    session = session_factory()
    stream = BybitWebSocketClient(url=settings.bybit_ws_url)
    metrics = SetaMetrics()
    metrics_server = start_metrics_server(
        metrics, host=settings.paper_metrics_host, port=settings.paper_metrics_port
    )

    async def _connect_subscribed() -> None:
        await stream.connect()
        for symbol in symbols:
            await stream.subscribe_kline(symbol, timeframe)
        metrics.set_connected(True)

    supervisor = ConnectionSupervisor(SupervisorConfig(), connect=_connect_subscribed)
    try:
        repo = SqlAlchemyPaperTradeEventRepository(session)
        config = PaperRunnerConfig(
            trading_mode=settings.trading_mode,
            live_trading_enabled=settings.live_trading_enabled,
            symbols=tuple(symbols),
            timeframe=timeframe.label,
            session_id=resolve_session_id(settings, timeframe, symbols[0]),
            decision_source=settings.paper_decision_source,
            report_interval_seconds=settings.paper_report_interval_hours * 60 * 60,
            max_runtime_seconds=seconds,
        )
        runner = PaperRunner(config=config, event_repo=repo)
        await supervisor.run_once_until_connected()
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
            recover=supervisor.run_once_until_connected,
            metrics=metrics,
            stale_timeout_seconds=settings.paper_stale_timeout_seconds,
        )
    finally:
        metrics_server.shutdown()
        metrics_server.server_close()
        await session.close()
        await engine.dispose()
        await stream.close()


def run_paper_runner(settings: Settings, argv: list[str] | None = None, run: RunFn = _run) -> int:
    parser = argparse.ArgumentParser(prog="paper-runner")
    parser.add_argument("--symbols", nargs="+", default=None)
    parser.add_argument("--timeframe", default=None)
    parser.add_argument("--seconds", type=int, default=None)
    parser.add_argument("--session-id", default=None)
    args = parser.parse_args(argv)
    if args.session_id is not None:
        settings = settings.model_copy(update={"paper_session_id": args.session_id})
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

from __future__ import annotations

import argparse
import asyncio
import json
import urllib.request
from collections.abc import Awaitable, Callable, Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from application.ports.market_repositories import MarketCandleRepository
from application.ports.market_stream import WebSocketDisconnected
from application.ports.paper_trading import PaperTradeEvent, PaperTradeEventRepository
from application.services.accounting_reconciliation import (
    MissingMarkError,
    latest_persisted_mark,
    reconcile_with_book,
)
from application.services.backfill import BackfillService
from application.services.certification_snapshot import (
    RuntimeArtifact,
    build_certification_state_v2,
    certification_phase,
    runtime_artifact,
    start_certification,
    write_certification_state_v2,
)
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
from application.services.recovery import recover_and_handoff, restore_runner
from domain.market.candle import Timeframe
from domain.market.stream import KlineUpdate
from domain.risk.config import RiskConfig
from domain.trading.strategy import EmaRsiBaseline
from infrastructure.bybit.client import BybitRestClient
from infrastructure.bybit.ws import BybitWebSocketClient
from infrastructure.database.repositories import (
    SqlAlchemyMarketCandleRepository,
    SqlAlchemyPaperTradeEventRepository,
    SqlAlchemySystemStateRepository,
)
from infrastructure.database.session import build_session_factory, create_engine
from infrastructure.observability.logging import (
    BUY_FILL,
    EXCEPTION,
    IMPORTANT_RISK_REJECTION,
    PROCESS_START,
    PROCESS_STOP,
    SELL_FILL,
    STATE_RESTORED,
    WS_CONNECTED,
    WS_DISCONNECTED,
    WS_RECONNECTED,
    WS_STALE,
    StructuredLogger,
    configure_json_logging,
    is_important_risk_rejection,
)
from infrastructure.observability.metrics import SetaMetrics
from infrastructure.observability.server import start_metrics_server
from settings import Settings

RunFn = Callable[..., Coroutine[Any, Any, str]]
SECONDS_PER_DAY = 24 * 60 * 60
MIN_RUNTIME_FOR_CERTIFICATION_DAYS = 45
_CERTIFICATION_STATE_SKIPPED = "CERTIFICATION_STATE_SKIPPED"
_CERT_START_REJECTED = "CERT_START_REJECTED"


def _certification_write_kind(state_path: Path) -> str:
    """Routing legacy/v2 por el ARCHIVO (Task 8b/B), nunca por params de wiring.

    - Fichero ausente o con ``schema_version == 2`` ⇒ ``"v2"`` (productor v2).
    - Fichero legacy plano (existe sin ``schema_version``) o ilegible ⇒ ``"legacy"``
      (escritor de compatibilidad 0.1.x). Un fichero corrupto no confirma schema 2
      y se trata como legacy (fail-closed al formato previo, que preserva el fichero).
    """
    if not state_path.exists():
        return "v2"
    try:
        previous = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return "legacy"
    if isinstance(previous, dict) and previous.get("schema_version") == 2:
        return "v2"
    return "legacy"


def resolve_runtime_seconds(cli_seconds: int | None, max_days: int) -> int | None:
    """Segundos de runtime del runner; ``None`` significa sin límite (unlimited)."""
    if cli_seconds is not None:
        return cli_seconds
    if max_days == 0:
        return None
    return max_days * SECONDS_PER_DAY


def preflight_runtime(*, max_days: int, session_id: str | None) -> None:
    """Aborta el arranque de una certificación con runtime insuficiente (D1)."""
    if session_id and 0 < max_days < MIN_RUNTIME_FOR_CERTIFICATION_DAYS:
        raise ValueError(
            "runtime configurado insuficiente para certificación: "
            f"paper_max_runtime_days = {max_days} < "
            f"{MIN_RUNTIME_FOR_CERTIFICATION_DAYS} "
            "(ventana 30d + margen 15d); usar 45 o 0=unlimited"
        )


def _default_session_id(timeframe: str, first_symbol: str) -> str:
    return f"paper-baseline-{timeframe}-{first_symbol.lower()}"


def resolve_session_id(settings: Settings, timeframe: Timeframe, first_symbol: str) -> str:
    if settings.paper_session_id:
        return settings.paper_session_id
    return _default_session_id(timeframe.label, first_symbol)


async def _restore_logged(
    *,
    restore: Callable[[], Awaitable[PaperRunner]],
    logger: StructuredLogger,
) -> PaperRunner:
    """Restaura el runner; loguea EXCEPTION si el recovery falla (no silencioso)."""
    try:
        runner = await restore()
    except Exception:
        logger.exception(EXCEPTION)
        raise
    logger.info(STATE_RESTORED)
    return runner


def _self_scrape_heartbeat_ok(metrics_port: int) -> bool:
    """Self-scrape del endpoint /metrics: True si el server responde 2xx.

    Nunca lanza: cualquier fallo de red/timeout/HTTP ⇒ False (ese día no cuenta
    cobertura), el runner jamás aborta por un heartbeat caído.
    """
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{metrics_port}/metrics", timeout=2.0
        ) as response:
            return 200 <= int(response.status) < 300
    except Exception:
        return False


def _read_safeguard_evidence(path: Path | None) -> dict[str, Any]:
    """Evidencia de safeguard drills; ausente/ilegible ⇒ {} (fail-closed)."""
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


async def _write_certification_state_v2(
    *,
    session_id: str,
    state_path: Path,
    summary: PaperRunSummary,
    events: list[PaperTradeEvent],
    candle_repo: MarketCandleRepository,
    artifact: RuntimeArtifact,
    symbol: str,
    timeframe: Timeframe,
    report_path: Path,
    heartbeat_ok_override: bool | None,
    metrics_port: int | None,
    safeguard_evidence_path: Path | None,
    logger: StructuredLogger | None,
) -> None:
    """Compone y escribe el certification-state v2 (schema 2) con el productor real.

    Fail-closed: los errores inesperados se propagan al caller (que los registra
    sin fabricar evidencia ni alterar trading); MissingMarkError se traduce a un
    estado ``accounting_status == FAIL`` con ``failure_reason`` y jamás crash.
    """
    previous = load_certification_state(state_path)
    phase = certification_phase(previous)
    if phase == "INVALIDATED":
        if logger is not None:
            logger.warning(
                _CERTIFICATION_STATE_SKIPPED,
                reason="previous state INVALIDATED; periodic v2 write skipped",
                state=str(state_path),
            )
        else:
            print(
                "[paper-runner] WARN: certification state INVALIDATED; "
                "periodic v2 write skipped (reactivate with --start-certification)"
            )
        return
    if heartbeat_ok_override is not None:
        heartbeat_ok = heartbeat_ok_override
    elif metrics_port is not None:
        heartbeat_ok = await asyncio.to_thread(_self_scrape_heartbeat_ok, metrics_port)
    else:
        heartbeat_ok = False
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    candles = await candle_repo.session_range(
        session_id=session_id, symbol=symbol, timeframe=timeframe, start_ms=0, end_ms=now_ms
    )
    interval_ms = timeframe.minutes * 60_000
    try:
        reconciliation = reconcile_with_book(
            events,
            initial_capital=RiskConfig().capital,
            mark_price=latest_persisted_mark(candles),
            previous_book=previous.get("accounting_book"),
            interval_ms=interval_ms,
        )
        reconciliation_error = None
    except MissingMarkError:
        reconciliation = None
        reconciliation_error = "missing_persisted_mark"
    state = build_certification_state_v2(
        previous=previous,
        summary=summary,
        events=events,
        candles=candles,
        heartbeat_ok=heartbeat_ok,
        today=today,
        safeguard_evidence=_read_safeguard_evidence(safeguard_evidence_path),
        reconciliation=reconciliation,
        reconciliation_error=reconciliation_error,
        artifact=artifact,
        now_ms=now_ms,
        interval_ms=interval_ms,
        report_path=str(report_path),
    )
    write_certification_state_v2(state, state_path)


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
    logger: StructuredLogger | None = None,
    candle_repo: MarketCandleRepository | None = None,
    artifact: RuntimeArtifact | None = None,
    symbol: str | None = None,
    timeframe: Timeframe | None = None,
    metrics_port: int | None = None,
    heartbeat_ok: bool | None = None,
    safeguard_evidence_path: Path | None = None,
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
            if logger is not None:
                logger.warning(WS_STALE)
            if recover is None:
                raise
            await recover()
            if metrics is not None:
                metrics.set_connected(True)
            if logger is not None:
                logger.info(WS_RECONNECTED)
            continue
        except WebSocketDisconnected as exc:
            if metrics is not None:
                metrics.inc_error("ws")
                metrics.inc_reconnect()
                metrics.set_connected(False)
            if logger is not None:
                logger.error(WS_DISCONNECTED, reason=str(exc))
            if recover is None:
                raise
            await recover()
            if metrics is not None:
                metrics.set_connected(True)
            if logger is not None:
                logger.info(WS_RECONNECTED)
            continue
        if not isinstance(event, KlineUpdate):
            continue
        try:
            paper_event = await runner.handle_kline(event)
        except Exception:
            if logger is not None:
                logger.exception(EXCEPTION)
            raise
        if paper_event is not None:
            processed += 1
            if metrics is not None:
                metrics.inc_candle()
                metrics.set_atr_ready(runner.atr_ready)
            if logger is not None:
                if paper_event.filled and paper_event.action == "BUY":
                    logger.info(
                        BUY_FILL,
                        symbol=paper_event.symbol,
                        exec_price=paper_event.exec_price,
                        quantity=paper_event.quantity,
                    )
                elif paper_event.filled and paper_event.action == "SELL":
                    logger.info(
                        SELL_FILL,
                        symbol=paper_event.symbol,
                        exec_price=paper_event.exec_price,
                        quantity=paper_event.quantity,
                        exit_reason=paper_event.exit_reason,
                    )
                elif is_important_risk_rejection(paper_event.risk_reason):
                    logger.warning(
                        IMPORTANT_RISK_REJECTION,
                        risk_reason=paper_event.risk_reason,
                    )
            try:
                await commit()
            except Exception:
                if logger is not None:
                    logger.exception(EXCEPTION)
                raise
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
                if _certification_write_kind(state_path) == "v2":
                    if (
                        candle_repo is None
                        or artifact is None
                        or symbol is None
                        or timeframe is None
                    ):
                        raise RuntimeError(
                            "certification v2 writer requires candle_repo/artifact/symbol/timeframe"
                        )
                    await _write_certification_state_v2(
                        session_id=session_id,
                        state_path=state_path,
                        summary=summary,
                        events=events,
                        candle_repo=candle_repo,
                        artifact=artifact,
                        symbol=symbol,
                        timeframe=timeframe,
                        report_path=report_path,
                        heartbeat_ok_override=heartbeat_ok,
                        metrics_port=metrics_port,
                        safeguard_evidence_path=safeguard_evidence_path,
                        logger=logger,
                    )
                else:
                    write_certification_state(
                        summary,
                        state_path,
                        previous=load_certification_state(state_path),
                        regime_evidence=runner.regime_evidence(),
                        report_path=report_path,
                    )
                last_summary = summary
                last_report_time = now
            except Exception as exc:
                if logger is not None:
                    logger.error(EXCEPTION, message=f"report write failed: {exc}")
                else:
                    print(f"[paper-runner] WARN: report write failed: {exc}")
    return f"processed={processed}"


def _operator_start_anchor(
    *,
    state_path: Path,
    artifact: RuntimeArtifact,
    now_ms: int,
    logger: StructuredLogger | None = None,
) -> bool:
    """Ancla el reloj v2 SOLO si el operador pidió --start-certification.

    NOT_STARTED/INVALIDATED con artefacto válido ⇒ start_certification + write v2
    (retorna True). RUNNING ⇒ no-op (nunca re-ancla; retorna False). START RECHAZADO
    (Task 8b/A: campo obligatorio vacío o conflicto de sesión con el estado
    persistido) ⇒ registra el rechazo para el operador y NO ancla (retorna False;
    el fichero queda intacto). Sin estado previo ({}).
    """
    previous = load_certification_state(state_path)
    phase = certification_phase(previous)
    if phase not in ("NOT_STARTED", "INVALIDATED"):
        if logger is not None:
            logger.info("CERT_START_SKIPPED", phase=phase)
        return False
    try:
        anchored = start_certification(previous, artifact, now_ms=now_ms)
    except ValueError as exc:
        if logger is not None:
            logger.warning(_CERT_START_REJECTED, reason=str(exc))
        else:
            print(f"[paper-runner] WARN: {exc}")
        return False
    write_certification_state_v2(anchored, state_path)
    if logger is not None:
        logger.info("CERT_STARTED", phase=phase)
    return True


async def _run(
    settings: Settings,
    symbols: list[str],
    timeframe: Timeframe,
    seconds: int | None,
    start_certification: bool = False,
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
        logger.info(WS_CONNECTED)

    supervisor = ConnectionSupervisor(SupervisorConfig(), connect=_connect_subscribed)
    session_id = resolve_session_id(settings, timeframe, symbols[0])
    logger = StructuredLogger(
        configure_json_logging(),
        context={
            "session_id": session_id,
            "symbol": symbols[0],
            "timeframe": timeframe.label,
            "application_version": settings.app_version,
            "strategy_version": "baseline-v1",
            "risk_config_version": RiskConfig().version,
        },
    )
    logger.info(PROCESS_START)
    try:
        repo = SqlAlchemyPaperTradeEventRepository(session)
        candle_repo = SqlAlchemyMarketCandleRepository(session)
        system_state_repo = SqlAlchemySystemStateRepository(session)
        rest_client = BybitRestClient(base_url=settings.bybit_base_url)
        config = PaperRunnerConfig(
            trading_mode=settings.trading_mode,
            live_trading_enabled=settings.live_trading_enabled,
            symbols=tuple(symbols),
            timeframe=timeframe.label,
            session_id=session_id,
            decision_source=settings.paper_decision_source,
            report_interval_seconds=settings.paper_report_interval_hours * 60 * 60,
            max_runtime_seconds=seconds,
        )
        runner = await _restore_logged(
            restore=lambda: restore_runner(
                config=config,
                event_repo=repo,
                candle_repo=candle_repo,
                system_state_repo=system_state_repo,
                symbol=symbols[0],
                timeframe=timeframe,
            ),
            logger=logger,
        )
        backfill_svc = BackfillService(rest_client, candle_repo)

        def _now_ms() -> int:
            return int(datetime.now(UTC).timestamp() * 1000)

        async def _backfill(*, cutoff_ms: int) -> None:
            await backfill_svc.backfill(
                session_id=config.session_id,
                symbol=symbols[0],
                timeframe=timeframe,
                cutoff_ms=cutoff_ms,
                runner=runner,
            )

        await recover_and_handoff(
            backfill=_backfill,
            subscribe=supervisor.run_once_until_connected,
            now_ms=_now_ms,
        )
        state_path = Path(settings.paper_certification_state_path)
        startup_events = await repo.list_session(config.session_id)
        startup_summary = summarize_events(startup_events, initial_equity=RiskConfig().capital)
        artifact = runtime_artifact(
            summary=startup_summary,
            app_version=settings.app_version,
            git_commit=settings.git_commit,
            docker_image_digest=settings.docker_image_digest,
            risk_config=RiskConfig(),
            now_ms=_now_ms(),
            default_symbol=symbols[0],
            default_timeframe=timeframe.label,
            default_strategy_version=EmaRsiBaseline.version,
            default_session_id=session_id,
        )
        if start_certification:
            _operator_start_anchor(
                state_path=state_path,
                artifact=artifact,
                now_ms=_now_ms(),
                logger=logger,
            )
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
            state_path=state_path,
            initial_equity=RiskConfig().capital,
            deadline=deadline,
            recover=supervisor.run_once_until_connected,
            metrics=metrics,
            stale_timeout_seconds=settings.paper_stale_timeout_seconds,
            logger=logger,
            candle_repo=candle_repo,
            artifact=artifact,
            symbol=symbols[0],
            timeframe=timeframe,
            metrics_port=settings.paper_metrics_port,
            safeguard_evidence_path=Path(settings.paper_safeguard_evidence_path),
        )
    finally:
        logger.info(PROCESS_STOP)
        metrics_server.shutdown()
        metrics_server.server_close()
        await session.close()
        await engine.dispose()
        await stream.close()
        await rest_client.close()


def run_paper_runner(settings: Settings, argv: list[str] | None = None, run: RunFn = _run) -> int:
    parser = argparse.ArgumentParser(prog="paper-runner")
    parser.add_argument("--symbols", nargs="+", default=None)
    parser.add_argument("--timeframe", default=None)
    parser.add_argument("--seconds", type=int, default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument(
        "--start-certification",
        action="store_true",
        default=False,
        help="ancla el reloj de certificación v2 antes del bucle (operador)",
    )
    args = parser.parse_args(argv)
    if args.session_id is not None:
        settings = settings.model_copy(update={"paper_session_id": args.session_id})
    try:
        preflight_runtime(
            max_days=settings.paper_max_runtime_days,
            session_id=settings.paper_session_id,
        )
        timeframe = Timeframe.from_label(args.timeframe or settings.paper_timeframe)
        symbols = args.symbols or list(settings.paper_symbols)
        max_runtime_seconds = resolve_runtime_seconds(args.seconds, settings.paper_max_runtime_days)
        if run is _run:
            result = asyncio.run(
                _run(
                    settings,
                    symbols,
                    timeframe,
                    max_runtime_seconds,
                    start_certification=args.start_certification,
                )
            )
        else:
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

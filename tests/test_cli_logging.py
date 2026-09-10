import asyncio
import io
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from application.ports.market_stream import WebSocketDisconnected
from application.ports.paper_trading import PaperTradeEvent
from application.services.paper_runner import PaperRunner, RecoveryDivergenceError
from domain.market.candle import Timeframe
from domain.market.stream import KlineUpdate
from infrastructure.observability.logging import (
    BUY_FILL,
    EXCEPTION,
    IMPORTANT_RISK_REJECTION,
    SELL_FILL,
    STATE_RESTORED,
    WS_DISCONNECTED,
    WS_RECONNECTED,
    JsonFormatter,
    StructuredLogger,
)
from interfaces.cli.paper_runner import _restore_logged, _run_loop


def _kline(close: float, ts: int) -> KlineUpdate:
    return KlineUpdate("ETHUSDT", Timeframe.M15, ts, close, close, close, close, 10.0, 1000.0, True)


class _Stream:
    def __init__(self, items: list[object]) -> None:
        self._items = list(items)

    async def recv(self) -> object:
        if not self._items:
            await asyncio.sleep(0.05)
            return None
        item = self._items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class _FakeRunner:
    """Runner duck-typed que devuelve eventos controlados."""

    def __init__(self, events: list[PaperTradeEvent | None]) -> None:
        self._events = list(events)
        self.atr_ready = False

    async def handle_kline(self, kline: KlineUpdate) -> PaperTradeEvent | None:
        if self._events:
            return self._events.pop(0)
        return None

    def regime_evidence(self) -> list[dict[str, Any]]:
        return []

    @property
    def rejected_regime_candidates(self) -> int:
        return 0


def _event(**overrides: object) -> PaperTradeEvent:
    base: dict[str, object] = dict(
        session_id="s",
        strategy_version="baseline-v1",
        strategy_hash="h",
        decision_source="baseline",
        symbol="ETHUSDT",
        timeframe="15m",
        timestamp_ms=1,
        action="HOLD",
        filled=False,
        risk_reason="",
        exit_reason="",
        exec_price=None,
        quantity=None,
        fee=0.0,
        slippage_cost=0.0,
        equity=1000.0,
        kill_switch_active=False,
    )
    base.update(overrides)
    return PaperTradeEvent(**base)  # type: ignore[arg-type]


def _logger() -> tuple[StructuredLogger, io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger(f"cli-logging-{id(stream)}")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
    return StructuredLogger(logger, context={"session_id": "s"}), stream


def _events(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


async def _run(
    tmp_path: Path,
    *,
    stream: _Stream,
    runner: _FakeRunner,
    logger: StructuredLogger,
    recover: Callable[[], Awaitable[None]] | None = None,
    commit: Callable[[], Awaitable[None]] | None = None,
) -> None:
    await _run_loop(
        stream=stream,
        runner=runner,  # type: ignore[arg-type]  # fake duck-typed
        repo=type("Repo", (), {"list_session": lambda *a, **k: []})(),
        commit=commit if commit is not None else lambda: asyncio.sleep(0),
        session_id="s",
        report_interval_seconds=3600,
        report_dir=tmp_path / "reports",
        state_path=tmp_path / "state.json",
        initial_equity=1000.0,
        deadline=asyncio.get_running_loop().time() + 1,
        logger=logger,
        recover=recover,
    )


async def test_run_loop_logs_ws_disconnect_and_reconnect(tmp_path: Path) -> None:
    logger, stream = _logger()
    runner = _FakeRunner([None, None])
    s = _Stream([_kline(100.0, 1), WebSocketDisconnected("drop"), _kline(101.0, 2)])

    async def recover() -> None:
        pass

    await _run(tmp_path, stream=s, runner=runner, logger=logger, recover=recover)

    records = _events(stream)
    names = [e["event"] for e in records]
    assert WS_DISCONNECTED in names
    assert WS_RECONNECTED in names
    # WS error → level=ERROR (no silencioso)
    ws_disconnect = next(e for e in records if e["event"] == WS_DISCONNECTED)
    assert ws_disconnect["level"] == "ERROR"


async def test_run_loop_logs_commit_error_as_exception(tmp_path: Path) -> None:
    logger, stream = _logger()
    runner = _FakeRunner([_event(action="HOLD", filled=False)])
    s = _Stream([_kline(100.0, 1)])

    async def failing_commit() -> None:
        raise RuntimeError("db commit failed")

    with pytest.raises(RuntimeError, match="db commit failed"):
        await _run(tmp_path, stream=s, runner=runner, logger=logger, commit=failing_commit)

    records = _events(stream)
    exc = next(e for e in records if e["event"] == EXCEPTION)
    assert exc["level"] == "ERROR"


async def test_run_loop_logs_buy_fill(tmp_path: Path) -> None:
    logger, stream = _logger()
    runner = _FakeRunner([_event(action="BUY", filled=True, exec_price=2503.33, quantity=0.008)])
    s = _Stream([_kline(100.0, 1)])

    await _run(tmp_path, stream=s, runner=runner, logger=logger)

    names = [e["event"] for e in _events(stream)]
    assert BUY_FILL in names
    assert SELL_FILL not in names


async def test_run_loop_logs_sell_fill(tmp_path: Path) -> None:
    logger, stream = _logger()
    runner = _FakeRunner(
        [
            _event(
                action="SELL",
                filled=True,
                exec_price=100.0,
                quantity=0.008,
                exit_reason="stop_loss",
            )
        ]
    )
    s = _Stream([_kline(100.0, 1)])

    await _run(tmp_path, stream=s, runner=runner, logger=logger)

    names = [e["event"] for e in _events(stream)]
    assert SELL_FILL in names


async def test_run_loop_logs_important_risk_rejection(tmp_path: Path) -> None:
    logger, stream = _logger()
    runner = _FakeRunner([_event(action="BUY", filled=False, risk_reason="max_daily_loss")])
    s = _Stream([_kline(100.0, 1)])

    await _run(tmp_path, stream=s, runner=runner, logger=logger)

    records = _events(stream)
    assert any(e["event"] == IMPORTANT_RISK_REJECTION for e in records)


async def test_run_loop_does_not_log_hold(tmp_path: Path) -> None:
    logger, stream = _logger()
    runner = _FakeRunner([_event(action="HOLD", filled=False, risk_reason="")])
    s = _Stream([_kline(100.0, 1)])

    await _run(tmp_path, stream=s, runner=runner, logger=logger)

    names = [e["event"] for e in _events(stream)]
    assert "HOLD" not in names


async def test_run_loop_logs_exception_and_propagates(tmp_path: Path) -> None:
    logger, stream = _logger()

    class ExplodingRunner(_FakeRunner):
        async def handle_kline(self, kline: KlineUpdate) -> PaperTradeEvent | None:
            raise ValueError("boom")

    s = _Stream([_kline(100.0, 1)])

    with pytest.raises(ValueError, match="boom"):
        await _run(tmp_path, stream=s, runner=ExplodingRunner([]), logger=logger)

    records = _events(stream)
    assert any(e["event"] == EXCEPTION for e in records)


async def test_restore_error_logged_as_exception() -> None:
    logger, stream = _logger()

    async def failing_restore() -> PaperRunner:
        raise RecoveryDivergenceError("replay diverge")

    with pytest.raises(RecoveryDivergenceError):
        await _restore_logged(restore=failing_restore, logger=logger)

    records = _events(stream)
    exc = next(e for e in records if e["event"] == EXCEPTION)
    assert exc["level"] == "ERROR"
    assert STATE_RESTORED not in [e["event"] for e in records]


class _EmptyEventRepo:
    async def add(self, event: PaperTradeEvent) -> None:
        pass

    async def list_session(self, session_id: str) -> list[PaperTradeEvent]:
        return []


async def test_restore_success_logs_state_restored() -> None:
    from application.services.paper_runner import PaperRunnerConfig

    logger, stream = _logger()
    config = PaperRunnerConfig(
        trading_mode="paper",
        live_trading_enabled=False,
        symbols=("ETHUSDT",),
        timeframe="15m",
        session_id="s",
    )
    runner = PaperRunner(config=config, event_repo=_EmptyEventRepo())

    async def ok_restore() -> PaperRunner:
        return runner

    await _restore_logged(restore=ok_restore, logger=logger)

    records = _events(stream)
    assert STATE_RESTORED in [e["event"] for e in records]

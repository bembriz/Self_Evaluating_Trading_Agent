import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from application.ports.market_stream import WebSocketDisconnected
from application.services.paper_runner import (
    PaperRunner,
    PaperRunnerConfig,
)
from domain.market.candle import Timeframe
from domain.market.stream import KlineUpdate
from interfaces.cli.paper_runner import (
    _default_session_id,
    _run_loop,
    paper_runner,
    resolve_session_id,
    run_paper_runner,
)
from settings import Settings


class FakeStream:
    def __init__(self, events: list[Any]) -> None:
        self._events = list(events)

    async def recv(self) -> Any:
        if not self._events:
            await asyncio.sleep(0.05)
            return None
        return self._events.pop(0)

    async def connect(self) -> None:
        pass

    async def subscribe_kline(self, symbol: str, timeframe: Timeframe) -> None:
        pass

    async def close(self) -> None:
        pass


class FakeRepo:
    def __init__(self, events: list[Any]) -> None:
        self._events = events

    async def add(self, event: Any) -> None:
        self._events.append(event)

    async def list_session(self, session_id: str) -> list[Any]:
        return list(self._events)


def _kline(close: float, ts: int, confirm: bool = True) -> KlineUpdate:
    return KlineUpdate(
        "ETHUSDT", Timeframe.M15, ts, close, close, close, close, 10.0, 1000.0, confirm
    )


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
        report_interval_seconds=0,
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


async def test_run_loop_preserves_existing_certification_evidence(tmp_path: Path) -> None:
    repo = FakeRepo([])
    stream = FakeStream([_kline(100.0, 1_000)])
    report_dir = tmp_path / "reports"
    state_path = tmp_path / "certification-state.json"
    state_path.write_text(
        json.dumps(
            {
                "market_regimes": [
                    {
                        "name": "SIDEWAYS",
                        "symbol": "ETHUSDT",
                        "timeframe": "15m",
                        "first_seen_at_ms": 1_000,
                        "confirmed_at_ms": 3_000,
                        "last_seen_at_ms": 3_000,
                        "classifier_version": "regime-v1",
                        "confirmation_candles": 3,
                    }
                ],
                "periodic_reports": [],
            }
        ),
        encoding="utf-8",
    )

    async def fake_commit() -> None:
        pass

    await _run_loop(
        stream=stream,
        runner=_paper_runner(repo),
        repo=repo,
        commit=fake_commit,
        session_id="paper-baseline-test",
        report_interval_seconds=0,
        report_dir=report_dir,
        state_path=state_path,
        initial_equity=1000.0,
        deadline=asyncio.get_running_loop().time() + 1,
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert [item["name"] for item in state["market_regimes"]] == ["SIDEWAYS"]
    assert len(state["periodic_reports"]) == 1


async def test_run_loop_preserves_corrupt_certification_state(tmp_path: Path) -> None:
    repo = FakeRepo([])
    stream = FakeStream([_kline(100.0, 1_000)])
    report_dir = tmp_path / "reports"
    state_path = tmp_path / "certification-state.json"
    state_path.write_text("{", encoding="utf-8")

    async def fake_commit() -> None:
        pass

    result = await _run_loop(
        stream=stream,
        runner=_paper_runner(repo),
        repo=repo,
        commit=fake_commit,
        session_id="paper-baseline-test",
        report_interval_seconds=0,
        report_dir=report_dir,
        state_path=state_path,
        initial_equity=1000.0,
        deadline=asyncio.get_running_loop().time() + 1,
    )

    assert result.startswith("processed=")
    assert state_path.read_text(encoding="utf-8") == "{"
    assert len(list(report_dir.glob("paper-*.md"))) == 1


class FailingStream(FakeStream):
    def __init__(self, events: list[Any]) -> None:
        super().__init__(events)
        self.reconnect_calls = 0

    async def recv(self) -> Any:
        if self._events:
            item = self._events.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item
        await asyncio.sleep(0.05)
        return None


async def test_run_loop_recovers_from_ws_disconnect_and_continues(tmp_path: Path) -> None:
    repo = FakeRepo([])
    stream = FailingStream(
        [
            _kline(100.0, 1_000),
            WebSocketDisconnected("keepalive ping timeout"),
            _kline(101.0, 2_000),
            _kline(102.0, 3_000),
        ]
    )

    async def recover() -> None:
        stream.reconnect_calls += 1

    async def fake_commit() -> None:
        pass

    result = await _run_loop(
        stream=stream,
        runner=_paper_runner(repo),
        repo=repo,
        commit=fake_commit,
        session_id="paper-baseline-test",
        report_interval_seconds=3600,
        report_dir=tmp_path / "reports",
        state_path=tmp_path / "certification-state.json",
        initial_equity=1000.0,
        deadline=asyncio.get_running_loop().time() + 1,
        recover=recover,
    )

    assert stream.reconnect_calls == 1
    assert result == "processed=3"
    assert len(repo._events) == 3


async def test_run_loop_preserves_runner_state_across_reconnect(tmp_path: Path) -> None:
    repo = FakeRepo([])
    stream = FailingStream(
        [
            _kline(100.0, 1_000),
            WebSocketDisconnected("drop"),
            _kline(101.0, 2_000),
        ]
    )

    async def recover() -> None:
        stream.reconnect_calls += 1

    async def fake_commit() -> None:
        pass

    runner = _paper_runner(repo)
    await _run_loop(
        stream=stream,
        runner=runner,
        repo=repo,
        commit=fake_commit,
        session_id="paper-baseline-test",
        report_interval_seconds=3600,
        report_dir=tmp_path / "reports",
        state_path=tmp_path / "certification-state.json",
        initial_equity=1000.0,
        deadline=asyncio.get_running_loop().time() + 1,
        recover=recover,
    )

    assert stream.reconnect_calls == 1
    assert len(runner._candles_by_symbol["ETHUSDT"]) == 2


async def test_run_loop_without_recover_propagates_disconnect(tmp_path: Path) -> None:
    repo = FakeRepo([])
    stream = FailingStream([WebSocketDisconnected("drop")])

    async def fake_commit() -> None:
        pass

    try:
        await _run_loop(
            stream=stream,
            runner=_paper_runner(repo),
            repo=repo,
            commit=fake_commit,
            session_id="paper-baseline-test",
            report_interval_seconds=3600,
            report_dir=tmp_path / "reports",
            state_path=tmp_path / "certification-state.json",
            initial_equity=1000.0,
            deadline=asyncio.get_running_loop().time() + 1,
        )
    except WebSocketDisconnected:
        return
    raise AssertionError("WebSocketDisconnected debe propagarse sin recover")


def test_paper_runner_help_exits_zero() -> None:
    try:
        paper_runner(["--help"])
    except SystemExit as exc:
        assert exc.code == 0


def test_paper_runner_rejects_invalid_timeframe() -> None:
    code = paper_runner(["--timeframe", "5m", "--seconds", "1"])
    assert code == 2


def test_run_paper_runner_accepts_injected_runtime() -> None:
    captured: dict[str, object] = {}

    async def fake_run(
        settings: Settings, symbols: list[str], timeframe: Timeframe, seconds: int | None
    ) -> str:
        captured["settings"] = settings
        captured["symbols"] = symbols
        captured["timeframe"] = timeframe
        captured["seconds"] = seconds
        return "processed=0"

    settings = Settings(trading_mode="paper", live_trading_enabled=False)

    code = run_paper_runner(
        settings,
        argv=["--symbols", "ETHUSDT", "--timeframe", "15m", "--seconds", "1"],
        run=fake_run,
    )

    assert code == 0
    assert captured == {
        "settings": settings,
        "symbols": ["ETHUSDT"],
        "timeframe": Timeframe.M15,
        "seconds": 1,
    }


def test_run_paper_runner_uses_max_runtime_days_when_seconds_omitted() -> None:
    captured: dict[str, object] = {}

    async def fake_run(
        settings: Settings, symbols: list[str], timeframe: Timeframe, seconds: int | None
    ) -> str:
        captured["seconds"] = seconds
        return "processed=0"

    settings = Settings(
        trading_mode="paper",
        live_trading_enabled=False,
        paper_max_runtime_days=7,
    )

    code = run_paper_runner(settings, argv=[], run=fake_run)

    assert code == 0
    assert captured["seconds"] == 604800


def test_default_session_id_derives_from_timeframe_and_symbol() -> None:
    assert _default_session_id("15m", "ETHUSDT") == "paper-baseline-15m-ethusdt"


def test_resolve_session_id_uses_settings_override_when_present() -> None:
    settings = Settings(
        trading_mode="paper",
        live_trading_enabled=False,
        paper_session_id="paper-baseline-20260906",
    )

    resolved = resolve_session_id(settings, Timeframe.M15, "ETHUSDT")

    assert resolved == "paper-baseline-20260906"


def test_resolve_session_id_falls_back_to_default_without_override() -> None:
    settings = Settings(trading_mode="paper", live_trading_enabled=False)

    resolved = resolve_session_id(settings, Timeframe.M15, "ETHUSDT")

    assert resolved == "paper-baseline-15m-ethusdt"


def test_run_paper_runner_forwards_cli_session_id_to_runtime() -> None:
    captured: dict[str, object] = {}

    async def fake_run(
        settings: Settings, symbols: list[str], timeframe: Timeframe, seconds: int | None
    ) -> str:
        captured["session_id"] = settings.paper_session_id
        return "processed=0"

    settings = Settings(trading_mode="paper", live_trading_enabled=False)

    code = run_paper_runner(
        settings,
        argv=["--session-id", "paper-baseline-20260906"],
        run=fake_run,
    )

    assert code == 0
    assert captured["session_id"] == "paper-baseline-20260906"


def test_run_paper_runner_cli_session_id_overrides_settings_env() -> None:
    captured: dict[str, object] = {}

    async def fake_run(
        settings: Settings, symbols: list[str], timeframe: Timeframe, seconds: int | None
    ) -> str:
        captured["session_id"] = settings.paper_session_id
        return "processed=0"

    settings = Settings(
        trading_mode="paper",
        live_trading_enabled=False,
        paper_session_id="paper-baseline-from-env",
    )

    code = run_paper_runner(
        settings,
        argv=["--session-id", "paper-baseline-20260906"],
        run=fake_run,
    )

    assert code == 0
    assert captured["session_id"] == "paper-baseline-20260906"


def test_run_paper_runner_keeps_env_session_id_without_cli_arg() -> None:
    captured: dict[str, object] = {}

    async def fake_run(
        settings: Settings, symbols: list[str], timeframe: Timeframe, seconds: int | None
    ) -> str:
        captured["session_id"] = settings.paper_session_id
        return "processed=0"

    settings = Settings(
        trading_mode="paper",
        live_trading_enabled=False,
        paper_session_id="paper-baseline-from-env",
    )

    code = run_paper_runner(settings, argv=[], run=fake_run)

    assert code == 0
    assert captured["session_id"] == "paper-baseline-from-env"


async def test_run_loop_stops_on_commit_failure(tmp_path: Path) -> None:
    repo = FakeRepo([])
    stream = FakeStream([_kline(100.0, 1_000), _kline(101.0, 2_000)])

    async def failing_commit() -> None:
        raise RuntimeError("db commit failed")

    with pytest.raises(RuntimeError, match="db commit failed"):
        await _run_loop(
            stream=stream,
            runner=_paper_runner(repo),
            repo=repo,
            commit=failing_commit,
            session_id="paper-baseline-test",
            report_interval_seconds=3600,
            report_dir=tmp_path / "reports",
            state_path=tmp_path / "certification-state.json",
            initial_equity=1000.0,
            deadline=asyncio.get_running_loop().time() + 1,
        )

    # El runner no procesa la segunda vela tras el fallo de commit.
    assert len(repo._events) == 1

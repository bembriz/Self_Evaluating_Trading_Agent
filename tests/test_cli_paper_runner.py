import asyncio
from pathlib import Path
from typing import Any

from application.services.paper_runner import (
    PaperRunner,
    PaperRunnerConfig,
)
from domain.market.candle import Timeframe
from domain.market.stream import KlineUpdate
from interfaces.cli.paper_runner import _run_loop, paper_runner, run_paper_runner
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

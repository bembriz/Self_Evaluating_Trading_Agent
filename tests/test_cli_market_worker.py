import pytest

from domain.market.candle import Timeframe
from interfaces.cli import market_worker as mw
from interfaces.cli.market_worker import run_with_reconnect


async def test_reconnect_with_backoff_then_success() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    async def run_once() -> str:
        calls["n"] += 1
        if calls["n"] <= 3:
            raise RuntimeError("boom")
        return "healthy"

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    health = await run_with_reconnect(run_once, seconds=100.0, sleep=sleep)
    assert health == "healthy"
    assert calls["n"] == 4
    assert sleeps == [1.0, 2.0, 4.0]


async def test_reconnect_caps_delay() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    async def run_once() -> str:
        calls["n"] += 1
        raise RuntimeError("boom")

    async def sleep(delay: float) -> None:
        sleeps.append(delay)
        if len(sleeps) >= 6:
            raise _Stop

    with pytest.raises(_Stop):
        await run_with_reconnect(run_once, seconds=10_000.0, sleep=sleep)
    assert sleeps[-1] == 30.0


async def test_reconnect_zero_seconds_returns_na() -> None:
    async def run_once() -> str:
        raise AssertionError("no debe llamarse")

    health = await run_with_reconnect(run_once, seconds=0.0)
    assert health == "n/a"


class _Stop(Exception):
    pass


def test_market_worker_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        mw.market_worker(["--help"])
    assert exc.value.code == 0


def test_market_worker_invalid_timeframe_raises() -> None:
    with pytest.raises(ValueError):
        mw.market_worker(["--seconds", "1", "--timeframes", "5m"])


def test_build_service_composes(monkeypatch: pytest.MonkeyPatch) -> None:
    from settings import Settings

    service, stream, engine, session = mw._build_service(Settings())
    try:
        assert service is not None
        assert stream is not None
        assert engine is not None
        assert session is not None
    finally:
        import asyncio

        asyncio.run(_dispose(session, engine, stream))


async def _dispose(session: object, engine: object, stream: object) -> None:
    await session.close()  # type: ignore[attr-defined]
    await engine.dispose()  # type: ignore[attr-defined]
    await stream.close()  # type: ignore[attr-defined]


async def test_session_run_returns_health(monkeypatch: pytest.MonkeyPatch) -> None:
    from settings import Settings

    class FakeService:
        health = "healthy"

        async def run(self, symbols: list[str], timeframes: list[Timeframe]) -> None:
            return None

    class FakeStream:
        async def close(self) -> None:
            return None

    class FakeEngine:
        async def dispose(self) -> None:
            return None

    class FakeSession:
        async def close(self) -> None:
            return None

    monkeypatch.setattr(
        mw, "_build_service", lambda s: (FakeService(), FakeStream(), FakeEngine(), FakeSession())
    )
    health = await mw._session_run(Settings(), ["ETHUSDT"], [Timeframe.M15])
    assert health == "healthy"


def test_market_worker_body(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def fake_reconnect(run_once: object, seconds: float, sleep: object = None) -> str:
        del run_once, seconds, sleep
        return "healthy"

    monkeypatch.setattr(mw, "run_with_reconnect", fake_reconnect)
    assert mw.market_worker(["--seconds", "1"]) == 0
    assert "health final: healthy" in capsys.readouterr().out

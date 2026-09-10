import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from application.ports.market_stream import WebSocketDisconnected
from application.ports.paper_trading import PaperTradeEvent
from application.services.certification_snapshot import (
    RuntimeArtifact,
    certification_phase,
    runtime_artifact,
)
from application.services.paper_runner import (
    PaperRunner,
    PaperRunnerConfig,
    summarize_events,
)
from domain.market.candle import Candle, Timeframe
from domain.market.stream import KlineUpdate
from domain.risk.config import RiskConfig
from domain.trading.strategy import EmaRsiBaseline
from interfaces.cli.paper_runner import (
    _certification_write_kind,
    _default_session_id,
    _operator_start_anchor,
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


def _candle(close: float, ts: int) -> Candle:
    return Candle(
        timestamp_ms=ts,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=10.0,
        turnover=close * 10.0,
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


class _StaticCandleRepo:
    """Candle repo in-memory: devuelve una lista fija en session_range."""

    def __init__(self, candles: list[Candle] | None = None) -> None:
        self._candles = candles or []

    async def upsert(self, symbol: str, timeframe: Timeframe, candles: list[Candle]) -> int:
        return 0

    async def count(self, symbol: str, timeframe: Timeframe) -> int:
        return len(self._candles)

    async def range(
        self, symbol: str, timeframe: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        return [c for c in self._candles if start_ms <= c.timestamp_ms <= end_ms]

    async def upsert_paper(
        self,
        session_id: str,
        symbol: str,
        timeframe: Timeframe,
        candles: list[Candle],
    ) -> int:
        return 0

    async def session_range(
        self,
        session_id: str,
        symbol: str,
        timeframe: Timeframe,
        start_ms: int,
        end_ms: int,
    ) -> list[Candle]:
        return [c for c in self._candles if start_ms <= c.timestamp_ms <= end_ms]

    async def last_persisted_ms(
        self, session_id: str, symbol: str, timeframe: Timeframe
    ) -> int | None:
        return None


class _StaticRunner:
    """Runner duck-typed que NO genera eventos (los repos llevan los seeds)."""

    atr_ready = False

    async def handle_kline(self, kline: KlineUpdate) -> PaperTradeEvent | None:
        return None

    def regime_evidence(self) -> list[dict[str, Any]]:
        return []

    @property
    def rejected_regime_candidates(self) -> int:
        return 0


def _event(
    action: str,
    timestamp_ms: int,
    *,
    filled: bool = False,
    exec_price: float | None = None,
    quantity: float | None = None,
    equity: float = 1000.0,
    fee: float = 0.0,
) -> PaperTradeEvent:
    return PaperTradeEvent(
        session_id="paper-baseline-test",
        strategy_version="baseline-v1",
        strategy_hash="h" * 64,
        decision_source="baseline",
        symbol="ETHUSDT",
        timeframe="15m",
        timestamp_ms=timestamp_ms,
        action=action,
        filled=filled,
        risk_reason="",
        exit_reason="",
        exec_price=exec_price,
        quantity=quantity,
        fee=fee,
        slippage_cost=0.0,
        equity=equity,
        kill_switch_active=False,
    )


def _artifact(events: list[PaperTradeEvent], now_ms: int) -> Any:
    summary = summarize_events(events, initial_equity=RiskConfig().capital)
    return runtime_artifact(
        summary=summary,
        app_version="0.2.0-test",
        git_commit="abc1234",
        docker_image_digest="sha256:deadbeef",
        risk_config=RiskConfig(),
        now_ms=now_ms,
    )


def _iso(now_ms: int) -> str:
    return datetime.fromtimestamp(now_ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


async def _run_periodic(
    tmp_path: Path,
    *,
    events: list[PaperTradeEvent],
    state_path: Path,
    candles: list[Candle] | None = None,
    heartbeat_ok: bool = False,
) -> str:
    """Ejecuta _run_loop con interval 0 (una escritura periódica) sobre repos in-memory."""
    repo = FakeRepo(list(events))
    stream = FakeStream([_kline(100.0, 1_000)])
    artifact = _artifact(events, now_ms=1_700_000_000_000)
    result = await _run_loop(
        stream=stream,
        runner=_StaticRunner(),  # type: ignore[arg-type]
        repo=repo,
        commit=lambda: asyncio.sleep(0),
        session_id="paper-baseline-test",
        report_interval_seconds=0,
        report_dir=tmp_path / "reports",
        state_path=state_path,
        initial_equity=RiskConfig().capital,
        deadline=asyncio.get_running_loop().time() + 0.2,
        candle_repo=_StaticCandleRepo(candles),
        artifact=artifact,
        symbol="ETHUSDT",
        timeframe=Timeframe.M15,
        heartbeat_ok=heartbeat_ok,
    )
    return result


async def test_periodic_write_without_flag_produces_not_started_v2(tmp_path: Path) -> None:
    """Periodic write sin flag → schema v2 + NOT_STARTED + claves legacy presentes."""
    events = [_event("HOLD", 1_000)]
    state_path = tmp_path / "certification-state.json"
    await _run_periodic(tmp_path, events=events, state_path=state_path)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["schema_version"] == 2
    assert certification_phase(state) == "NOT_STARTED"
    for key in (
        "strategy_version",
        "active_strategy_hash",
        "calendar_days",
        "trade_count",
        "market_regimes",
        "periodic_reports",
        "latest_equity",
        "initial_equity",
    ):
        assert key in state, f"clave legacy ausente: {key}"


async def test_operator_start_anchors_and_is_idempotent(tmp_path: Path) -> None:
    """--start-certification ancla RUNNING; segundo start con distinto now_ms NO re-ancla."""
    events = [_event("HOLD", 1_000)]
    state_path = tmp_path / "certification-state.json"
    artifact = _artifact(events, now_ms=1_700_000_000_000)

    assert await _run_periodic(tmp_path, events=events, state_path=state_path)
    assert certification_phase(json.loads(state_path.read_text())) == "NOT_STARTED"

    first = _operator_start_anchor(state_path=state_path, artifact=artifact, now_ms=1_000)
    assert first is True
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert certification_phase(state) == "RUNNING"
    anchor = state["frozen"]["certification_started_at"]
    assert anchor == _iso(1_000)

    second = _operator_start_anchor(state_path=state_path, artifact=artifact, now_ms=99_999)
    assert second is False
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert certification_phase(state) == "RUNNING"
    assert state["frozen"]["certification_started_at"] == anchor


async def test_restart_recompose_preserves_anchor(tmp_path: Path) -> None:
    """Recargar estado RUNNING + recomponer periódicamente ⇒ mismo anchor (restart)."""
    events = [_event("HOLD", 1_000)]
    state_path = tmp_path / "certification-state.json"
    artifact = _artifact(events, now_ms=1_700_000_000_000)

    await _run_periodic(tmp_path, events=events, state_path=state_path)
    assert _operator_start_anchor(state_path=state_path, artifact=artifact, now_ms=1_000)
    anchor = json.loads(state_path.read_text())["frozen"]["certification_started_at"]

    await _run_periodic(tmp_path, events=events, state_path=state_path)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert certification_phase(state) == "RUNNING"
    assert state["frozen"]["certification_started_at"] == anchor


async def test_invalidated_new_start_creates_new_anchor(tmp_path: Path) -> None:
    """INVALIDATED + nuevo --start-certification ⇒ anchor nuevo (no el previo)."""
    events = [_event("HOLD", 1_000)]
    artifact = _artifact(events, now_ms=1_700_000_000_000)
    old_anchor = _iso(42)
    state_path = tmp_path / "certification-state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "status": "INVALIDATED",
                "invalidated_reason": "operator",
                "frozen": {
                    "symbol": "ETHUSDT",
                    "timeframe": "15m",
                    "certification_started_at": old_anchor,
                },
                "current": {},
            }
        ),
        encoding="utf-8",
    )

    assert _operator_start_anchor(state_path=state_path, artifact=artifact, now_ms=5_000)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert certification_phase(state) == "RUNNING"
    assert state["frozen"]["certification_started_at"] == _iso(5_000)
    assert state["frozen"]["certification_started_at"] != old_anchor


async def test_two_periodic_runs_with_different_now_keep_frozen_identical(tmp_path: Path) -> None:
    """Dos corridas periódicas (distinto now_ms) conservan `frozen` idéntico (sin re-ancla)."""
    events = [_event("HOLD", 1_000)]
    state_path = tmp_path / "certification-state.json"
    artifact = _artifact(events, now_ms=1_700_000_000_000)

    await _run_periodic(tmp_path, events=events, state_path=state_path)
    assert _operator_start_anchor(state_path=state_path, artifact=artifact, now_ms=1_000)
    anchor = json.loads(state_path.read_text())["frozen"]["certification_started_at"]

    await _run_periodic(tmp_path, events=events, state_path=state_path)
    frozen1 = json.loads(state_path.read_text())["frozen"]
    await _run_periodic(tmp_path, events=events, state_path=state_path)
    frozen2 = json.loads(state_path.read_text())["frozen"]
    assert frozen1 == frozen2
    assert frozen1["certification_started_at"] == anchor


async def test_missing_candle_with_open_position_fails_closed(tmp_path: Path) -> None:
    """Posición abierta sin velas persistidas ⇒ missing_persisted_mark, sin crash ni NaN."""
    events = [_event("BUY", 1_000, filled=True, exec_price=100.0, quantity=0.5, equity=950.0)]
    state_path = tmp_path / "certification-state.json"
    result = await _run_periodic(tmp_path, events=events, state_path=state_path)
    assert result.startswith("processed=")

    state = json.loads(state_path.read_text(encoding="utf-8"))
    operational = state["operational"]
    assert operational["accounting_residual"] is None
    assert operational["accounting_status"] == "FAIL"
    assert operational["accounting_failure_reason"] == "missing_persisted_mark"
    json.dumps(state, allow_nan=False)  # no lanza


async def test_periodic_write_over_invalidated_previous_is_not_rewritten(tmp_path: Path) -> None:
    """Guard: una escritura periódica sobre un estado INVALIDATED NO lo reactiva."""
    events = [_event("HOLD", 1_000)]
    state_path = tmp_path / "certification-state.json"
    original = {
        "schema_version": 2,
        "status": "INVALIDATED",
        "invalidated_reason": "operator",
        "frozen": {
            "symbol": "ETHUSDT",
            "timeframe": "15m",
            "certification_started_at": _iso(42),
        },
        "current": {},
        "operational": {},
        "accounting_book": None,
    }
    state_path.write_text(json.dumps(original), encoding="utf-8")

    await _run_periodic(tmp_path, events=events, state_path=state_path)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert certification_phase(state) == "INVALIDATED"
    assert state["status"] == "INVALIDATED"
    assert state["frozen"]["certification_started_at"] == _iso(42)


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
        candle_repo=_StaticCandleRepo([]),
        artifact=_config_artifact([], now_ms=1_700_000_000_000),
        symbol="ETHUSDT",
        timeframe=Timeframe.M15,
        heartbeat_ok=False,
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


def test_run_paper_runner_accepts_start_certification_flag() -> None:
    """El flag --start-certification se parsea sin romper la inyección del runnable."""
    called: list[tuple[object, ...]] = []

    async def fake_run(
        settings: Settings, symbols: list[str], timeframe: Timeframe, seconds: int | None
    ) -> str:
        called.append((settings, symbols, timeframe, seconds))
        return "processed=0"

    settings = Settings(trading_mode="paper", live_trading_enabled=False)

    code = run_paper_runner(
        settings,
        argv=["--start-certification", "--seconds", "1"],
        run=fake_run,
    )

    assert code == 0
    assert len(called) == 1


def test_run_paper_runner_help_mentions_start_certification(
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(trading_mode="paper", live_trading_enabled=False)
    try:
        run_paper_runner(settings, argv=["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    out = capsys.readouterr().out
    assert "--start-certification" in out


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


# ---------------------------------------------------------------------------
# Task 8b/A: identidad al START (resolución persistido-else-config en el CLI)
# ---------------------------------------------------------------------------


def _config_artifact(
    events: list[PaperTradeEvent],
    now_ms: int,
    *,
    symbol: str = "ETHUSDT",
    timeframe: str = "15m",
    strategy_version: str = EmaRsiBaseline.version,
    git_commit: str = "abc1234",
) -> RuntimeArtifact:
    """Artefacto como lo construye _run: identidad = resumen persistido no vacío
    ELSE config (`symbols[0]`, `timeframe.label`, `EmaRsiBaseline.version`)."""
    summary = summarize_events(events, initial_equity=RiskConfig().capital)
    return runtime_artifact(
        summary=summary,
        app_version="0.2.0-test",
        git_commit=git_commit,
        docker_image_digest="sha256:deadbeef",
        risk_config=RiskConfig(),
        now_ms=now_ms,
        default_symbol=symbol,
        default_timeframe=timeframe,
        default_strategy_version=strategy_version,
    )


async def test_operator_start_pristine_session_anchors_config_identity(tmp_path: Path) -> None:
    """(A/CLI) Sesión prístina (0 eventos, sin fichero) ⇒ START ancla con identidad de config."""
    state_path = tmp_path / "certification-state.json"
    artifact = _config_artifact([], now_ms=1_700_000_000_000)
    assert artifact.symbol == "ETHUSDT"
    assert artifact.timeframe == "15m"
    assert artifact.strategy_version == "baseline-v1"

    assert _operator_start_anchor(state_path=state_path, artifact=artifact, now_ms=1_000)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert certification_phase(state) == "RUNNING"
    assert state["frozen"]["certification_started_at"] == _iso(1_000)
    assert state["frozen"]["symbol"] == "ETHUSDT"
    assert state["frozen"]["timeframe"] == "15m"
    assert state["frozen"]["strategy_version"] == "baseline-v1"


async def test_operator_start_missing_mandatory_field_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """(A/CLI) Falta un campo obligatorio (git_commit vacío) ⇒ rechazo, sin fichero/ancla."""
    state_path = tmp_path / "certification-state.json"
    artifact = _config_artifact([], now_ms=1_700_000_000_000, git_commit="")
    assert not state_path.exists()

    assert _operator_start_anchor(state_path=state_path, artifact=artifact, now_ms=1_000) is False
    assert not state_path.exists()
    out = capsys.readouterr().out
    assert "START rejected" in out


async def test_operator_start_rejected_over_conflicting_not_started_session(
    tmp_path: Path,
) -> None:
    """(A/CLI) Estado NOT_STARTED de otra sesión (ETH) + config BTC ⇒ rechazo sin ancla."""
    state_path = tmp_path / "certification-state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "session_id": "paper-baseline-15m-ethusdt",
                "application_version": "0.2.0",
                "status": None,
                "invalidated_reason": None,
                "frozen": {
                    "symbol": "ETHUSDT",
                    "timeframe": "15m",
                    "application_version": "0.2.0-test",
                    "strategy_version": "baseline-v1",
                    "certification_started_at": None,
                },
                "current": {},
            }
        ),
        encoding="utf-8",
    )

    artifact = _config_artifact([], now_ms=1_700_000_000_000, symbol="BTCUSDT")
    assert _operator_start_anchor(state_path=state_path, artifact=artifact, now_ms=5_000) is False

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["frozen"]["symbol"] == "ETHUSDT"
    assert state["frozen"]["certification_started_at"] is None
    assert certification_phase(state) == "NOT_STARTED"


async def test_operator_start_running_context_mismatch_never_reanchors(tmp_path: Path) -> None:
    """(8d/4-CLI) RUNNING anclado + config de otra sesión ⇒ no-op: ancla intacta, sin re-ancla."""
    state_path = tmp_path / "certification-state.json"
    eth = _config_artifact([], now_ms=1_700_000_000_000, symbol="ETHUSDT")
    assert _operator_start_anchor(state_path=state_path, artifact=eth, now_ms=1_000)
    before = json.loads(state_path.read_text(encoding="utf-8"))
    anchor = before["frozen"]["certification_started_at"]
    assert certification_phase(before) == "RUNNING"

    btc = _config_artifact([], now_ms=1_700_000_000_000, symbol="BTCUSDT")
    assert _operator_start_anchor(state_path=state_path, artifact=btc, now_ms=99_999) is False

    after = json.loads(state_path.read_text(encoding="utf-8"))
    assert after == before  # ni re-ancla ni muta el estado RUNNING
    assert after["frozen"]["certification_started_at"] == anchor
    assert after["frozen"]["symbol"] == "ETHUSDT"
    assert certification_phase(after) == "RUNNING"


async def test_operator_start_restart_preserves_identity_and_anchor(tmp_path: Path) -> None:
    """(A/CLI) Restart: segunda llamada con distinto now_ms conserva identidad + ancla."""
    state_path = tmp_path / "certification-state.json"
    artifact = _config_artifact([], now_ms=1_700_000_000_000)
    assert _operator_start_anchor(state_path=state_path, artifact=artifact, now_ms=1_000)
    first = json.loads(state_path.read_text(encoding="utf-8"))
    anchor = first["frozen"]["certification_started_at"]

    assert _operator_start_anchor(state_path=state_path, artifact=artifact, now_ms=99_999) is False
    again = json.loads(state_path.read_text(encoding="utf-8"))
    assert again["frozen"]["certification_started_at"] == anchor
    assert again["frozen"]["symbol"] == first["frozen"]["symbol"] == "ETHUSDT"
    assert again["frozen"]["timeframe"] == first["frozen"]["timeframe"] == "15m"
    assert (
        again["frozen"]["strategy_version"] == first["frozen"]["strategy_version"] == "baseline-v1"
    )


# ---------------------------------------------------------------------------
# Task 8b/B: routing legacy/v2 por schema del ARCHIVO (no por params de wiring)
# ---------------------------------------------------------------------------


async def test_routing_v2_file_uses_v2_writer(tmp_path: Path) -> None:
    """(B) Fichero con schema_version==2 (aunque mín./incompleto) ⇒ escritor v2."""
    events = [_event("HOLD", 1_000)]
    state_path = tmp_path / "certification-state.json"
    state_path.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")

    await _run_periodic(tmp_path, events=events, state_path=state_path)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["schema_version"] == 2
    assert "frozen" in state
    assert "current" in state
    assert "operational" in state
    assert state["frozen"]["certification_started_at"] is None


async def test_routing_legacy_flat_file_uses_legacy_writer(tmp_path: Path) -> None:
    """(B) Fichero legacy plano (sin schema_version) ⇒ legacy writer AUNQUE haya wiring v2."""
    events = [_event("HOLD", 1_000)]
    state_path = tmp_path / "certification-state.json"
    state_path.write_text(
        json.dumps({"market_regimes": [], "periodic_reports": []}), encoding="utf-8"
    )

    await _run_periodic(tmp_path, events=events, state_path=state_path)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "schema_version" not in state
    assert "frozen" not in state
    assert "operational" not in state
    assert "strategy_version" in state
    assert state["strategy_version"] == "baseline-v1"
    assert len(state["periodic_reports"]) == 1


def test_certification_write_kind_routes_by_file_schema() -> None:
    """(B) Decisión pura: ausente ⇒ v2; schema 2 ⇒ v2; legacy plano ⇒ legacy; corrupto ⇒ legacy."""
    assert _certification_write_kind(Path("/nonexistent/certification-state.json")) == "v2"

    v2 = Path("/tmp/phase16c-kind-v2.json")
    v2.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
    try:
        assert _certification_write_kind(v2) == "v2"
    finally:
        v2.unlink()

    legacy = Path("/tmp/phase16c-kind-legacy.json")
    legacy.write_text(json.dumps({"strategy_version": "baseline-v1"}), encoding="utf-8")
    try:
        assert _certification_write_kind(legacy) == "legacy"
    finally:
        legacy.unlink()

    corrupt = Path("/tmp/phase16c-kind-corrupt.json")
    corrupt.write_text("{", encoding="utf-8")
    try:
        assert _certification_write_kind(corrupt) == "legacy"
    finally:
        corrupt.unlink()


# ---------------------------------------------------------------------------
# Task 8c / F1: deploy fresco — start escribe schema_version:2 completo y el
# routing (Task 8b) permanece v2 tras la primera escritura periódica.
# ---------------------------------------------------------------------------


async def test_fresh_start_then_periodic_stays_v2_running(
    tmp_path: Path,
) -> None:
    """(F1/CLI) Sin fichero previo: --start-certification escribe un doc v2 COMPLETO
    (schema_version 2, no re-clasificable legacy) y la escritura periódica real
    (productor v2) lo conserva RUNNING con operational poblado (evidencia real).

    Regresión del deploy limpio 0.2.0: antes, el doc de START sin `schema_version`
    era reclasificado legacy por `_certification_write_kind` y el reloj v2 jamás
    progresaba.
    """
    events = [_event("HOLD", 1_000)]
    state_path = tmp_path / "certification-state.json"
    assert not state_path.exists()

    artifact = _artifact(events, now_ms=1_700_000_000_000)
    assert _operator_start_anchor(state_path=state_path, artifact=artifact, now_ms=1_000)

    started = json.loads(state_path.read_text(encoding="utf-8"))
    assert started["schema_version"] == 2
    assert certification_phase(started) == "RUNNING"
    assert started["session_id"] == "paper-baseline-test"
    assert started["session_started_at"] == _iso(1_000)
    # Simetría top-level con el productor periódico: identidad presente desde el
    # primer doc (sin FAIL espurio de state_continuity en la primera escritura).
    assert started["application_version"] == "0.2.0-test"
    assert set(started["frozen"]) == {
        "git_commit",
        "application_version",
        "strategy_version",
        "risk_config_version",
        "docker_image_digest",
        "symbol",
        "timeframe",
        "initial_capital",
        "fees_slippage_config_version",
        "certification_started_at",
    }
    assert isinstance(started["operational"], dict)
    assert "accounting_book" in started
    assert started["status"] is None
    json.dumps(started, allow_nan=False)  # strict JSON, sin NaN

    await _run_periodic(
        tmp_path,
        events=events,
        state_path=state_path,
        candles=[_candle(100.0, 1_000)],
        heartbeat_ok=True,
    )
    final = json.loads(state_path.read_text(encoding="utf-8"))
    assert _certification_write_kind(state_path) == "v2"  # routing NO deriva a legacy
    assert final["schema_version"] == 2
    assert certification_phase(final) == "RUNNING"
    assert final["frozen"]["certification_started_at"] == _iso(1_000)  # ancla intacta
    operational = final["operational"]
    assert operational["accounting_status"] == "PASS"
    assert operational["accounting_residual"] == "0"
    assert operational["state_continuity"] == "PASS"  # sin FAIL espurio en el 1er write
    assert operational["metrics_history_days"] >= 1  # heartbeat real confirmado
    json.dumps(final, allow_nan=False)

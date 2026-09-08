import pytest

from application.ports.paper_trading import PaperTradeEvent
from application.services.paper_runner import (
    PaperRunner,
    PaperRunnerConfig,
    RecoveryDivergenceError,
)
from application.services.recovery import KILL_SWITCH_KEY, recover_and_handoff, restore_runner
from domain.market.candle import Candle, Timeframe

TF = Timeframe.M15


def _candle(ts: int, close: float = 100.0) -> Candle:
    return Candle(ts, close - 1.0, close + 1.0, close - 2.0, close, 10.0, 1000.0)


class FakeCandleRepo:
    def __init__(self, candles: list[Candle] | None = None) -> None:
        self._candles = candles or []

    async def upsert(self, symbol: str, timeframe: Timeframe, candles: list[Candle]) -> int:
        return 0

    async def count(self, symbol: str, timeframe: Timeframe) -> int:
        return 0

    async def range(
        self, symbol: str, timeframe: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        return []

    async def session_range(
        self, session_id: str, symbol: str, timeframe: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        return list(self._candles)

    async def upsert_paper(
        self, session_id: str, symbol: str, timeframe: Timeframe, candles: list[Candle]
    ) -> int:
        return 0

    async def last_persisted_ms(
        self, session_id: str, symbol: str, timeframe: Timeframe
    ) -> int | None:
        return None


class FakeEventRepo:
    def __init__(self, events: list[PaperTradeEvent] | None = None) -> None:
        self.events = events or []

    async def add(self, event: PaperTradeEvent) -> None:
        self.events.append(event)

    async def list_session(self, session_id: str) -> list[PaperTradeEvent]:
        return [e for e in self.events if e.session_id == session_id]


class FakeSystemState:
    def __init__(self, data: dict[str, object] | None = None) -> None:
        self._data = data or {}

    async def get(self, key: str) -> dict[str, object] | None:
        value = self._data.get(key)
        return value if isinstance(value, dict) else None

    async def set(self, key: str, value: dict[str, object]) -> None:
        self._data[key] = value

    async def ping(self) -> bool:
        return True


def _config() -> PaperRunnerConfig:
    return PaperRunnerConfig(
        trading_mode="paper",
        live_trading_enabled=False,
        symbols=("ETHUSDT",),
        timeframe="15m",
        session_id="sess",
    )


def _live_events(candles: list[Candle]) -> list[PaperTradeEvent]:
    runner = PaperRunner(config=_config(), event_repo=FakeEventRepo())
    events: list[PaperTradeEvent] = []
    for c in candles:
        events.append(runner._process("ETHUSDT", TF.label, c))
    return events


async def test_restore_runner_restores_kill_switch() -> None:
    system = FakeSystemState(
        {KILL_SWITCH_KEY: {"active": True, "reason": "manual", "activated_at_ms": 42}}
    )

    runner = await restore_runner(
        config=_config(),
        event_repo=FakeEventRepo(),
        candle_repo=FakeCandleRepo(),
        system_state_repo=system,
        symbol="ETHUSDT",
        timeframe=TF,
    )

    assert runner._engine.kill_switch_state.active is True
    assert runner._engine.kill_switch_state.reason == "manual"


async def test_restore_runner_replays_events_without_divergence() -> None:
    candles = [_candle(i * 900_000, 100.0 + i * 0.5) for i in range(60)]
    events = _live_events(candles)

    runner = await restore_runner(
        config=_config(),
        event_repo=FakeEventRepo(events),
        candle_repo=FakeCandleRepo(candles),
        system_state_repo=FakeSystemState(),
        symbol="ETHUSDT",
        timeframe=TF,
    )

    assert runner._engine.kill_switch_state.active is False


async def test_restore_runner_detects_divergence() -> None:
    candles = [_candle(i * 900_000, 100.0 + i * 0.5) for i in range(3)]
    events = _live_events(candles)
    # Mutar un evento persistido para forzar divergencia.
    first = events[0]
    events[0] = PaperTradeEvent(
        session_id=first.session_id,
        strategy_version=first.strategy_version,
        strategy_hash=first.strategy_hash,
        decision_source=first.decision_source,
        symbol=first.symbol,
        timeframe=first.timeframe,
        timestamp_ms=first.timestamp_ms,
        action="BUY",
        filled=True,
        risk_reason="",
        exit_reason="",
        exec_price=100.0,
        quantity=0.1,
        fee=0.0,
        slippage_cost=0.0,
        equity=1000.0,
        kill_switch_active=False,
    )

    with pytest.raises(RecoveryDivergenceError):
        await restore_runner(
            config=_config(),
            event_repo=FakeEventRepo(events),
            candle_repo=FakeCandleRepo(candles),
            system_state_repo=FakeSystemState(),
            symbol="ETHUSDT",
            timeframe=TF,
        )


async def test_recover_and_handoff_sequence_closes_race() -> None:
    calls: list[tuple[str, int | None]] = []

    async def backfill(*, cutoff_ms: int) -> None:
        calls.append(("backfill", cutoff_ms))

    async def subscribe() -> None:
        calls.append(("subscribe", None))

    ticks = iter([1_000, 2_000])

    def now_ms() -> int:
        return next(ticks)

    await recover_and_handoff(backfill=backfill, subscribe=subscribe, now_ms=now_ms)

    assert [kind for kind, _ in calls] == ["backfill", "subscribe", "backfill"]

import pytest

from application.ports.paper_trading import PaperTradeEvent
from application.services.paper_runner import (
    PaperRunner,
    PaperRunnerConfig,
    RecoveryDivergenceError,
    RecoveryGapError,
    events_equivalent,
)
from domain.market.candle import Candle
from domain.market.stream import KlineUpdate


class FakePaperTradeRepo:
    def __init__(self) -> None:
        self.events: list[PaperTradeEvent] = []

    async def add(self, event: PaperTradeEvent) -> None:
        self.events.append(event)

    async def list_session(self, session_id: str) -> list[PaperTradeEvent]:
        return [e for e in self.events if e.session_id == session_id]


def _config() -> PaperRunnerConfig:
    return PaperRunnerConfig(
        trading_mode="paper",
        live_trading_enabled=False,
        symbols=("ETHUSDT",),
        timeframe="15m",
        session_id="paper-baseline-test",
    )


def _candle(i: int, close: float) -> Candle:
    ts = (i + 1) * 15 * 60 * 1000
    return Candle(ts, close - 0.5, close + 0.1, close - 0.6, close, 10.0, 1000.0)


def _uptrend(n: int, start: float = 100.0, step: float = 0.5) -> list[Candle]:
    return [_candle(i, start + i * step) for i in range(n)]


def _event_key(event: PaperTradeEvent) -> tuple[str, str, int]:
    return (event.symbol, event.timeframe, event.timestamp_ms)


def test_events_equivalent_identical() -> None:
    a = PaperTradeEvent(
        session_id="s",
        strategy_version="v",
        strategy_hash="h",
        decision_source="baseline",
        symbol="ETHUSDT",
        timeframe="15m",
        timestamp_ms=1,
        action="BUY",
        filled=True,
        risk_reason="",
        exit_reason="",
        exec_price=100.0,
        quantity=0.1,
        fee=0.02,
        slippage_cost=0.004,
        equity=999.9,
        kill_switch_active=False,
    )
    assert events_equivalent(a, a) is True


def test_events_equivalent_float_tolerance() -> None:
    base = PaperTradeEvent(
        session_id="s",
        strategy_version="v",
        strategy_hash="h",
        decision_source="baseline",
        symbol="ETHUSDT",
        timeframe="15m",
        timestamp_ms=1,
        action="SELL",
        filled=True,
        risk_reason="",
        exit_reason="stop_loss",
        exec_price=100.0,
        quantity=0.1,
        fee=0.02,
        slippage_cost=0.004,
        equity=999.9,
        kill_switch_active=False,
    )
    other = PaperTradeEvent(
        session_id="s",
        strategy_version="v",
        strategy_hash="h",
        decision_source="baseline",
        symbol="ETHUSDT",
        timeframe="15m",
        timestamp_ms=1,
        action="SELL",
        filled=True,
        risk_reason="",
        exit_reason="stop_loss",
        exec_price=100.0 + 1e-12,
        quantity=0.1,
        fee=0.02,
        slippage_cost=0.004,
        equity=999.9,
        kill_switch_active=False,
    )
    assert events_equivalent(base, other) is True


def test_events_equivalent_categorical_mismatch() -> None:
    a = PaperTradeEvent(
        session_id="s",
        strategy_version="v",
        strategy_hash="h",
        decision_source="baseline",
        symbol="ETHUSDT",
        timeframe="15m",
        timestamp_ms=1,
        action="BUY",
        filled=True,
        risk_reason="",
        exit_reason="",
        exec_price=100.0,
        quantity=0.1,
        fee=0.02,
        slippage_cost=0.004,
        equity=999.9,
        kill_switch_active=False,
    )
    b = PaperTradeEvent(
        session_id="s",
        strategy_version="v",
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
    assert events_equivalent(a, b) is False


def test_replay_reproduces_live_state() -> None:
    candles = _uptrend(80)
    live = PaperRunner(config=_config(), event_repo=FakePaperTradeRepo())
    events: list[PaperTradeEvent] = []
    for c in candles:
        event = live._process("ETHUSDT", "15m", c)
        assert event is not None
        events.append(event)

    persisted = {_event_key(e): e for e in events}

    replay = PaperRunner(config=_config(), event_repo=FakePaperTradeRepo())
    replay.replay([("ETHUSDT", "15m", c) for c in candles], persisted)

    # Continuidad: la siguiente vela debe producir el mismo evento en ambos.
    next_candle = _candle(80, 100.0 + 80 * 0.5 + 0.5)
    live_next = live._process("ETHUSDT", "15m", next_candle)
    replay_next = replay._process("ETHUSDT", "15m", next_candle)
    assert events_equivalent(live_next, replay_next) is True


def test_replay_detects_divergence() -> None:
    candle = _candle(0, 100.0)
    live = PaperRunner(config=_config(), event_repo=FakePaperTradeRepo())
    recomputed = live._process("ETHUSDT", "15m", candle)
    assert recomputed is not None

    diverged = PaperTradeEvent(
        session_id=recomputed.session_id,
        strategy_version=recomputed.strategy_version,
        strategy_hash=recomputed.strategy_hash,
        decision_source=recomputed.decision_source,
        symbol=recomputed.symbol,
        timeframe=recomputed.timeframe,
        timestamp_ms=recomputed.timestamp_ms,
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

    replay = PaperRunner(config=_config(), event_repo=FakePaperTradeRepo())
    with pytest.raises(RecoveryDivergenceError):
        replay.replay([("ETHUSDT", "15m", candle)], {_event_key(diverged): diverged})


def test_replay_detects_gap() -> None:
    candles = _uptrend(3)
    replay = PaperRunner(config=_config(), event_repo=FakePaperTradeRepo())
    with pytest.raises(RecoveryGapError):
        replay.replay([("ETHUSDT", "15m", c) for c in candles], {})


def test_kline_to_candle_confirmed_contract() -> None:
    # Contrato que usa el replay: las velas son Candle confirmados, no KlineUpdate.
    from domain.market.candle import Timeframe

    kline = KlineUpdate("ETHUSDT", Timeframe.M15, 1, 1.0, 2.0, 0.5, 1.5, 1.0, 1.0, True)
    candle = kline.to_candle()
    assert candle is not None

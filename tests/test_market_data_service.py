import pytest

from application.ports.market_stream import StreamEvent, WebSocketDisconnected
from application.services.market_data_service import MarketDataConfig, MarketDataService
from domain.market.candle import Candle, Timeframe
from domain.market.features import OrderBookFeatureSnapshot
from domain.market.orderbook import MarketDataHealth, OrderBookLevel
from domain.market.stream import KlineUpdate, OrderBookDelta, OrderBookSnapshot


class FakeStream:
    def __init__(self) -> None:
        self.subscribed_orderbook: list[tuple[str, int]] = []
        self.subscribed_kline: list[tuple[str, Timeframe]] = []

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def subscribe_orderbook(self, symbol: str, depth: int) -> None:
        self.subscribed_orderbook.append((symbol, depth))

    async def subscribe_kline(self, symbol: str, interval: Timeframe) -> None:
        self.subscribed_kline.append((symbol, interval))

    async def recv(self) -> StreamEvent:
        raise WebSocketDisconnected("no events")


class FakeCandleRepo:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, Timeframe, list[Candle]]] = []

    async def upsert(self, symbol: str, timeframe: Timeframe, candles: list[Candle]) -> int:
        self.upserts.append((symbol, timeframe, candles))
        return len(candles)

    async def count(self, symbol: str, timeframe: Timeframe) -> int:
        return 0

    async def range(
        self, symbol: str, timeframe: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        return []

    async def upsert_paper(
        self, session_id: str, symbol: str, timeframe: Timeframe, candles: list[Candle]
    ) -> int:
        return len(candles)

    async def session_range(
        self, session_id: str, symbol: str, timeframe: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        return []

    async def last_persisted_ms(
        self, session_id: str, symbol: str, timeframe: Timeframe
    ) -> int | None:
        return None


class FakeFeatureRepo:
    def __init__(self) -> None:
        self.inserted: list[OrderBookFeatureSnapshot] = []

    async def insert(self, feature: OrderBookFeatureSnapshot) -> None:
        self.inserted.append(feature)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def stream() -> FakeStream:
    return FakeStream()


@pytest.fixture
def candle_repo() -> FakeCandleRepo:
    return FakeCandleRepo()


@pytest.fixture
def feature_repo() -> FakeFeatureRepo:
    return FakeFeatureRepo()


@pytest.fixture
def service(
    stream: FakeStream, candle_repo: FakeCandleRepo, feature_repo: FakeFeatureRepo, clock: Clock
) -> MarketDataService:
    return MarketDataService(
        stream=stream,
        candle_repo=candle_repo,
        feature_repo=feature_repo,
        config=MarketDataConfig(stale_timeout_seconds=10.0),
        clock=clock,
    )


def snap(update_id: int) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol="ETHUSDT",
        bids=(OrderBookLevel(100.0, 1.0), OrderBookLevel(99.0, 2.0)),
        asks=(OrderBookLevel(101.0, 1.5), OrderBookLevel(102.0, 3.0)),
        update_id=update_id,
        seq=update_id,
    )


def delta(update_id: int) -> OrderBookDelta:
    return OrderBookDelta(
        symbol="ETHUSDT",
        bids=(OrderBookLevel(100.5, 2.0),),
        asks=(),
        update_id=update_id,
        seq=update_id,
    )


async def test_snapshot_marks_healthy(service: MarketDataService, clock: Clock) -> None:
    await service.handle_snapshot(snap(1))
    assert service.health == MarketDataHealth.HEALTHY


async def test_delta_gap_marks_stale(service: MarketDataService, clock: Clock) -> None:
    await service.handle_snapshot(snap(1))
    need_resub = await service.handle_delta(delta(5))
    assert need_resub is True
    assert service.health == MarketDataHealth.STALE


async def test_kline_confirm_upserts(
    service: MarketDataService, candle_repo: FakeCandleRepo, clock: Clock
) -> None:
    k = KlineUpdate("ETHUSDT", Timeframe.M15, 1000, 1.0, 2.0, 0.5, 1.5, 10.0, 20.0, confirm=True)
    candle = await service.handle_kline(k)
    assert candle is not None
    assert len(candle_repo.upserts) == 1


async def test_kline_unconfirmed_ignored(
    service: MarketDataService, candle_repo: FakeCandleRepo, clock: Clock
) -> None:
    k = KlineUpdate("ETHUSDT", Timeframe.M15, 1000, 1.0, 2.0, 0.5, 1.5, 10.0, 20.0, confirm=False)
    candle = await service.handle_kline(k)
    assert candle is None
    assert candle_repo.upserts == []


async def test_timeout_marks_stale(service: MarketDataService, clock: Clock) -> None:
    await service.handle_snapshot(snap(1))
    clock.now = 100.0  # > stale_timeout_seconds
    service.check_stale()
    assert service.health == MarketDataHealth.STALE


async def test_aggregate_features(
    service: MarketDataService, feature_repo: FakeFeatureRepo, clock: Clock
) -> None:
    await service.handle_snapshot(snap(1))
    snapshots = await service.aggregate_features(window_start_ms=0, window_end_ms=5000)
    assert len(snapshots) == 1
    f = snapshots[0]
    assert f.symbol == "ETHUSDT"
    assert f.best_bid == 100.0
    assert f.best_ask == 101.0
    assert f.bid_depth == 3.0
    assert f.ask_depth == 4.5
    assert len(feature_repo.inserted) == 1


async def test_handle_delta_without_snapshot_returns_true(
    service: MarketDataService, clock: Clock
) -> None:
    need_resub = await service.handle_delta(delta(2))
    assert need_resub is True
    assert service.health == MarketDataHealth.STALE


class FakeStreamWithRecv:
    def __init__(self, events: list[StreamEvent]) -> None:
        self.events = list(events)
        self.subscribed_orderbook: list[tuple[str, int]] = []
        self.subscribed_kline: list[tuple[str, Timeframe]] = []

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def subscribe_orderbook(self, symbol: str, depth: int) -> None:
        self.subscribed_orderbook.append((symbol, depth))

    async def subscribe_kline(self, symbol: str, interval: Timeframe) -> None:
        self.subscribed_kline.append((symbol, interval))

    async def recv(self) -> StreamEvent:
        if not self.events:
            raise WebSocketDisconnected("closed")
        return self.events.pop(0)


async def test_run_consumes_events_and_disconnects(candle_repo: FakeCandleRepo) -> None:
    kline = KlineUpdate(
        "ETHUSDT", Timeframe.M15, 1000, 1.0, 2.0, 0.5, 1.5, 10.0, 20.0, confirm=True
    )
    stream = FakeStreamWithRecv([snap(1), delta(2), kline])
    service = MarketDataService(
        stream=stream,
        candle_repo=candle_repo,
        feature_repo=FakeFeatureRepo(),
        config=MarketDataConfig(stale_timeout_seconds=10.0),
    )
    with pytest.raises(WebSocketDisconnected):
        await service.run(["ETHUSDT"], [Timeframe.M15])
    assert stream.subscribed_orderbook == [("ETHUSDT", 50)]
    assert stream.subscribed_kline == [("ETHUSDT", Timeframe.M15)]
    assert candle_repo.upserts
    assert service.health == MarketDataHealth.HEALTHY


async def test_commit_called_after_aggregation(candle_repo: FakeCandleRepo) -> None:
    commits: list[int] = []

    async def commit() -> None:
        commits.append(1)

    kline = KlineUpdate(
        "ETHUSDT", Timeframe.M15, 1000, 1.0, 2.0, 0.5, 1.5, 10.0, 20.0, confirm=True
    )
    stream = FakeStreamWithRecv([snap(1), delta(2), kline])
    service = MarketDataService(
        stream=stream,
        candle_repo=candle_repo,
        feature_repo=FakeFeatureRepo(),
        config=MarketDataConfig(feature_window_seconds=0),
        commit=commit,
    )
    with pytest.raises(WebSocketDisconnected):
        await service.run(["ETHUSDT"], [Timeframe.M15])
    assert commits

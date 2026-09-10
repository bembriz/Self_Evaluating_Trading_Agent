from application.ports.paper_trading import PaperTradeEvent
from application.services.backfill import BackfillResult, BackfillService, candle_close_ms
from application.services.paper_runner import PaperRunner, PaperRunnerConfig
from application.services.recovery import recover_and_handoff
from domain.market.candle import Candle, Timeframe

TF = Timeframe.M15
TF_MS = TF.minutes * 60_000


def _candle(ts: int, close: float = 100.0) -> Candle:
    return Candle(ts, close - 1.0, close + 1.0, close - 2.0, close, 10.0, 1000.0)


class FakeClient:
    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles
        self.calls: list[tuple[str, Timeframe, int, int]] = []

    async def fetch_candles(
        self, symbol: str, interval: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        self.calls.append((symbol, interval, start_ms, end_ms))
        return [c for c in self._candles if start_ms <= c.timestamp_ms <= end_ms]


class FakeSequenceClient:
    """Devuelve una lista distinta por llamada (simula el paso del tiempo)."""

    def __init__(self, batches: list[list[Candle]]) -> None:
        self._batches = batches
        self._i = 0
        self.calls: list[tuple[int, int]] = []

    async def fetch_candles(
        self, symbol: str, interval: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        self.calls.append((start_ms, end_ms))
        batch = self._batches[self._i] if self._i < len(self._batches) else []
        self._i += 1
        return [c for c in batch if start_ms <= c.timestamp_ms <= end_ms]


class FakeCandleRepo:
    def __init__(self) -> None:
        self._candles: dict[tuple[str, str, str, int], Candle] = {}

    async def upsert(self, symbol: str, timeframe: Timeframe, candles: list[Candle]) -> int:
        return 0

    async def count(self, symbol: str, timeframe: Timeframe) -> int:
        return 0

    async def range(
        self, symbol: str, timeframe: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        return []

    async def upsert_paper(
        self, session_id: str, symbol: str, timeframe: Timeframe, candles: list[Candle]
    ) -> int:
        inserted = 0
        for c in candles:
            key = (session_id, symbol, timeframe.label, c.timestamp_ms)
            if key not in self._candles:
                self._candles[key] = c
                inserted += 1
        return inserted

    async def session_range(
        self, session_id: str, symbol: str, timeframe: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        return [
            c
            for (sid, sym, tf, ts), c in self._candles.items()
            if sid == session_id
            and sym == symbol
            and tf == timeframe.label
            and start_ms <= ts <= end_ms
        ]

    async def last_persisted_ms(
        self, session_id: str, symbol: str, timeframe: Timeframe
    ) -> int | None:
        ts = [
            k[3]
            for k in self._candles
            if k[0] == session_id and k[1] == symbol and k[2] == timeframe.label
        ]
        return max(ts) if ts else None


class FakeEventRepo:
    def __init__(self) -> None:
        self.events: list[PaperTradeEvent] = []

    async def add(self, event: PaperTradeEvent) -> None:
        key = (event.session_id, event.symbol, event.timeframe, event.timestamp_ms)
        for existing in self.events:
            ek = (existing.session_id, existing.symbol, existing.timeframe, existing.timestamp_ms)
            if ek == key:
                return
        self.events.append(event)

    async def list_session(self, session_id: str) -> list[PaperTradeEvent]:
        return [e for e in self.events if e.session_id == session_id]


def _runner(events: FakeEventRepo, candles: FakeCandleRepo) -> PaperRunner:
    config = PaperRunnerConfig(
        trading_mode="paper",
        live_trading_enabled=False,
        symbols=("ETHUSDT",),
        timeframe="15m",
        session_id="sess",
    )
    return PaperRunner(config=config, event_repo=events, candle_repo=candles)


def test_candle_close_ms() -> None:
    assert candle_close_ms(900_000, TF) == 1_800_000


async def test_backfill_no_gap() -> None:
    candles = FakeCandleRepo()
    await candles.upsert_paper("sess", "ETHUSDT", TF, [_candle(900_000)])
    client = FakeClient([])
    events = FakeEventRepo()
    svc = BackfillService(client, candles)

    result = await svc.backfill(
        session_id="sess",
        symbol="ETHUSDT",
        timeframe=TF,
        cutoff_ms=1_800_000,
        runner=_runner(events, candles),
    )
    assert result.recovered == 0
    assert result.skipped_partial == 0


async def test_backfill_one_lost_candle() -> None:
    candles = FakeCandleRepo()
    await candles.upsert_paper("sess", "ETHUSDT", TF, [_candle(900_000)])
    client = FakeClient([_candle(1_800_000)])
    events = FakeEventRepo()
    svc = BackfillService(client, candles)

    result = await svc.backfill(
        session_id="sess",
        symbol="ETHUSDT",
        timeframe=TF,
        cutoff_ms=2_700_000,
        runner=_runner(events, candles),
    )
    assert result.recovered == 1
    assert len(events.events) == 1
    assert events.events[0].timestamp_ms == 1_800_000


async def test_backfill_multiple_lost_candles_in_order() -> None:
    candles = FakeCandleRepo()
    await candles.upsert_paper("sess", "ETHUSDT", TF, [_candle(0)])
    client = FakeClient([_candle(900_000), _candle(1_800_000), _candle(2_700_000)])
    events = FakeEventRepo()
    svc = BackfillService(client, candles)

    result = await svc.backfill(
        session_id="sess",
        symbol="ETHUSDT",
        timeframe=TF,
        cutoff_ms=3_600_000,
        runner=_runner(events, candles),
    )
    assert result.recovered == 3
    assert [e.timestamp_ms for e in events.events] == [900_000, 1_800_000, 2_700_000]


async def test_backfill_skips_partial_candle() -> None:
    candles = FakeCandleRepo()
    await candles.upsert_paper("sess", "ETHUSDT", TF, [_candle(900_000)])
    closed = _candle(1_800_000)  # close 2_700_000 <= cutoff
    partial = _candle(2_700_000)  # close 3_600_000 > cutoff (aún abierta)
    client = FakeClient([closed, partial])
    events = FakeEventRepo()
    svc = BackfillService(client, candles)

    result = await svc.backfill(
        session_id="sess",
        symbol="ETHUSDT",
        timeframe=TF,
        cutoff_ms=2_700_000,
        runner=_runner(events, candles),
    )
    assert result.recovered == 1
    assert result.skipped_partial == 1
    assert [e.timestamp_ms for e in events.events] == [1_800_000]


async def test_backfill_overlap_reprocess_is_idempotent() -> None:
    # Una vela ya persistida (reprocesada por solapamiento REST/WS) no duplica evento.
    candles = FakeCandleRepo()
    events = FakeEventRepo()
    runner = _runner(events, candles)

    await runner.handle_candle("ETHUSDT", TF, _candle(1_800_000))
    await runner.handle_candle("ETHUSDT", TF, _candle(1_800_000))

    assert len(events.events) == 1  # dedup por (session, symbol, tf, ts)


async def test_restart_no_gap_produces_no_new_events() -> None:
    # Restart sin gap: la última vela persistida ya está al corte → backfill vacío.
    candles = FakeCandleRepo()
    await candles.upsert_paper("sess", "ETHUSDT", TF, [_candle(900_000)])
    events = FakeEventRepo()
    client = FakeClient([])
    svc = BackfillService(client, candles)

    result = await svc.backfill(
        session_id="sess",
        symbol="ETHUSDT",
        timeframe=TF,
        cutoff_ms=1_800_000,
        runner=_runner(events, candles),
    )
    assert result.recovered == 0
    assert result.skipped_partial == 0
    assert len(events.events) == 0


async def test_fresh_session_never_fetches_history() -> None:
    """Sesión SIN velas persistidas: NO se consulta REST, NO se procesa, NO se persiste.

    Regresión del boundary de certificación: un ``last is None`` NO debe recuperar
    histórico desde ``start=0`` (contaminaría la sesión antes del anchor).
    """
    candles = FakeCandleRepo()  # sesión prístina: sin velas
    events = FakeEventRepo()
    client = FakeClient([_candle(900_000), _candle(1_800_000)])  # histórico disponible
    svc = BackfillService(client, candles)

    result = await svc.backfill(
        session_id="sess",
        symbol="ETHUSDT",
        timeframe=TF,
        cutoff_ms=2_700_000,
        runner=_runner(events, candles),
    )

    assert client.calls == []  # REST NO invocado
    assert result == BackfillResult(recovered=0, skipped_partial=0)
    assert events.events == []  # 0 events
    assert await candles.last_persisted_ms("sess", "ETHUSDT", TF) is None  # 0 candles


async def test_existing_session_backfills_only_from_last_plus_interval() -> None:
    """Sesión existente: el fetch arranca en ``last + interval`` (no en 0)."""
    candles = FakeCandleRepo()
    await candles.upsert_paper("sess", "ETHUSDT", TF, [_candle(900_000)])
    events = FakeEventRepo()
    client = FakeClient([_candle(1_800_000), _candle(2_700_000)])
    svc = BackfillService(client, candles)

    result = await svc.backfill(
        session_id="sess",
        symbol="ETHUSDT",
        timeframe=TF,
        cutoff_ms=3_600_000,
        runner=_runner(events, candles),
    )

    assert client.calls == [("ETHUSDT", TF, 1_800_000, 3_600_000)]
    assert result.recovered == 2
    assert [e.timestamp_ms for e in events.events] == [1_800_000, 2_700_000]


async def test_handoff_race_candle_closes_between_backfill_and_subscribe() -> None:
    # La vela cierra exactamente entre el backfill y la suscripción WS:
    # el segundo backfill (tras subscribe) la recupera exactamente una vez.
    candles = FakeCandleRepo()
    await candles.upsert_paper("sess", "ETHUSDT", TF, [_candle(900_000)])
    events = FakeEventRepo()
    runner = _runner(events, candles)

    # Primera llamada: la vela de 1_800_000 aún no cierra. Segunda: ya cerró.
    client = FakeSequenceClient([[], [_candle(1_800_000)]])
    svc = BackfillService(client, candles)
    cutoffs = iter([2_700_000, 3_600_000])
    subscribed: list[bool] = []

    async def backfill(*, cutoff_ms: int) -> None:
        await svc.backfill(
            session_id="sess",
            symbol="ETHUSDT",
            timeframe=TF,
            cutoff_ms=cutoff_ms,
            runner=runner,
        )

    async def subscribe() -> None:
        subscribed.append(True)

    def now_ms() -> int:
        return next(cutoffs)

    await recover_and_handoff(backfill=backfill, subscribe=subscribe, now_ms=now_ms)

    assert len(subscribed) == 1
    assert [e.timestamp_ms for e in events.events] == [1_800_000]

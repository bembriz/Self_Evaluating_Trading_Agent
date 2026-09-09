"""E2E integrado de recovery/auditabilidad (Fase 16c.5).

Prueba la garantía central del paper-runner restart-safe:

    NO_RESTART_TRACE == RESTART_TRACE

es decir, que un runner que reinicia a mitad de certificación (replay determinista
+ backfill del gap) reconstruye un estado *idéntico* al de una corrida continua,
sin duplicar ni perder fills, y que la evidencia de mercado (velas + decision_context)
queda persistida y es reconstruible/auditable.

Escenarios del PRD §76 / propuesta 16c §14.3:

- E2E-1  restart mid-position  → paridad total de estado + reconciliation residual 0
- E2E-2  restart daily-loss    → pérdida diaria y bloqueo de BUY preservados
- E2E-3  market evidence       → velas + decision_context persistidos y reconstruibles
- E2E-4  no-lookahead          → recompute(T) == snapshot(T)
- E2E-5  métricas requeridas   → familias Prometheus presentes tras corrida completa
- E2E-6/7/8  restart con gap 0/1/N → estado final idéntico al control, sin duplicados
- E2E-9  overlap REST/WS       → vela reentregada no duplica evento
- E2E-10 crash ANTES del commit → la vela no committeada se recupera por backfill
- kill switch sobrevive restart (MUST_HAVE)

Crash DESPUÉS del commit (D3, regresión de 16c.5a): la vela committeada que
reaparece por solapamiento es no-op — sin evento/fill/contabilidad duplicados y
paridad total de estado. Cubierto por el test de integración
``tests/integration/test_recovery_roundtrip.py::test_crash_after_commit_overlap_replayed_candle_is_noop``
(commit ``6eac3c7``), no se duplica aquí.

Usa repos in-memory + motor real (PaperEngine/RiskEngine/Portfolio deterministas);
sin red externa, sin LLM real. La variante con PostgreSQL real vive en
``tests/integration/test_recovery_roundtrip.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from application.ports.paper_trading import PaperTradeEvent
from application.services.backfill import BackfillService
from application.services.decision_context import DecisionContext, recompute_decision_contexts
from application.services.paper_engine import PaperEngine
from application.services.paper_runner import PaperRunner, PaperRunnerConfig
from application.services.recovery import KILL_SWITCH_KEY, restore_runner
from domain.market.candle import Candle, Timeframe
from domain.risk.config import RiskConfig
from domain.risk.guards import KillSwitch, KillSwitchState
from domain.trading.signal import Action
from domain.trading.strategy import PrecomputedStrategy

SYMBOL = "ETHUSDT"
TF = Timeframe.M15
TF_MS = TF.minutes * 60_000

_WARMUP = 15  # velas para completar el warmup de ATR (1 prev_close + 14 TR)


def _candle(i: int, close: float) -> Candle:
    ts = i * TF_MS
    return Candle(ts, close - 1.0, close + 1.0, close - 2.0, close, 10.0, 1000.0)


def _config(session_id: str) -> PaperRunnerConfig:
    return PaperRunnerConfig(
        trading_mode="paper",
        live_trading_enabled=False,
        symbols=(SYMBOL,),
        timeframe="15m",
        session_id=session_id,
    )


def _event_key(event: PaperTradeEvent) -> tuple[str, str, int]:
    return (event.symbol, event.timeframe, event.timestamp_ms)


class FakeCandleRepo:
    """Repositorio in-memory de velas con idempotencia por (session, symbol, tf, ts)."""

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
        for candle in candles:
            key = (session_id, symbol, timeframe.label, candle.timestamp_ms)
            if key not in self._candles:
                self._candles[key] = candle
                inserted += 1
        return inserted

    async def session_range(
        self, session_id: str, symbol: str, timeframe: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        return sorted(
            (
                candle
                for (sid, sym, tf, ts), candle in self._candles.items()
                if sid == session_id
                and sym == symbol
                and tf == timeframe.label
                and start_ms <= ts <= end_ms
            ),
            key=lambda candle: candle.timestamp_ms,
        )

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
    """Repositorio in-memory de eventos con dedup por (session, symbol, tf, ts)."""

    def __init__(self) -> None:
        self.events: list[PaperTradeEvent] = []

    async def add(self, event: PaperTradeEvent) -> None:
        key = (event.session_id, event.symbol, event.timeframe, event.timestamp_ms)
        if any((e.session_id, e.symbol, e.timeframe, e.timestamp_ms) == key for e in self.events):
            return
        self.events.append(event)

    async def list_session(self, session_id: str) -> list[PaperTradeEvent]:
        return [e for e in self.events if e.session_id == session_id]


class FakeSystemState:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data = data or {}

    async def get(self, key: str) -> dict[str, Any] | None:
        value = self._data.get(key)
        return value if isinstance(value, dict) else None

    async def set(self, key: str, value: dict[str, Any]) -> None:
        self._data[key] = value

    async def ping(self) -> bool:
        return True


class FakeClient:
    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles

    async def fetch_candles(
        self, symbol: str, interval: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        return [c for c in self._candles if start_ms <= c.timestamp_ms <= end_ms]


def _runner(
    session_id: str,
    actions: list[Action],
    engine_factory: Callable[[], PaperEngine],
    event_repo: FakeEventRepo,
    candle_repo: FakeCandleRepo,
) -> PaperRunner:
    return PaperRunner(
        config=_config(session_id),
        event_repo=event_repo,
        candle_repo=candle_repo,
        strategy=PrecomputedStrategy(actions),  # type: ignore[arg-type]
        paper_engine=engine_factory(),
    )


def _default_engine() -> PaperEngine:
    return PaperEngine(config=RiskConfig())


def _daily_loss_engine() -> PaperEngine:
    """Config que hace alcanzable la pérdida diaria con un solo trade perdedor."""
    return PaperEngine(
        config=replace(RiskConfig(), max_position_allocation=1.0, max_daily_loss=0.01)
    )


def _state(engine: PaperEngine) -> tuple[Any, ...]:
    pos = engine.position
    return (
        engine.portfolio.cash,
        engine.portfolio.position,
        engine.portfolio.avg_entry,
        engine.portfolio.realized_pnl,
        pos.quantity if pos is not None else None,
        pos.entry_price if pos is not None else None,
        pos.stop_loss if pos is not None else None,
        pos.highest_price if pos is not None else None,
        engine.realized_pnl_today,
        engine.daily_loss_active,
        engine.peak_equity,
    )


def _assert_state_equal(a: tuple[Any, ...], b: tuple[Any, ...]) -> None:
    for x, y in zip(a, b, strict=True):
        if x is None or y is None:
            assert x is y, f"state mismatch: {x!r} != {y!r}"
        elif isinstance(x, bool):
            assert x == y, f"state mismatch: {x!r} != {y!r}"
        else:
            assert x == pytest.approx(y, rel=1e-9, abs=1e-9), f"state mismatch: {x!r} != {y!r}"


@pytest.mark.e2e
async def test_e2e_1_restart_mid_position_full_state_parity() -> None:
    """BUY → restart → restore → SELL: estado completo idéntico + residual contable 0."""
    n = 22
    split = 20  # posición abierta (vela 15=BUY, 16..20=HOLD), SELL en vela 21
    actions = [Action.HOLD] * _WARMUP + [Action.BUY] + [Action.HOLD] * 5 + [Action.SELL]
    closes = [100.0] * _WARMUP + [100.0] + [101.0] * 5 + [102.0]
    candles = [_candle(i, closes[i]) for i in range(n)]

    control = _runner("ctrl", actions, _default_engine, FakeEventRepo(), FakeCandleRepo())
    for candle in candles:
        await control.handle_candle(SYMBOL, TF, candle)

    repo = FakeEventRepo()
    crepo = FakeCandleRepo()
    live = _runner("restart", actions, _default_engine, repo, crepo)
    for candle in candles[:split]:
        await live.handle_candle(SYMBOL, TF, candle)
    assert live._engine.position is not None  # a mitad de posición

    restored = _runner("restart", actions, _default_engine, repo, crepo)
    restored.replay(
        [(SYMBOL, TF.label, c) for c in candles[:split]], {_event_key(e): e for e in repo.events}
    )
    assert restored._engine.position is not None
    _assert_state_equal(_state(restored._engine), _state(live._engine))

    for candle in candles[split:]:
        await restored.handle_candle(SYMBOL, TF, candle)

    _assert_state_equal(_state(restored._engine), _state(control._engine))

    engine = restored._engine
    assert engine.portfolio.position == 0.0
    residual = (
        engine.portfolio.equity(closes[-1]) - RiskConfig().capital - engine.portfolio.realized_pnl
    )
    assert residual == pytest.approx(0.0, abs=1e-9)


@pytest.mark.e2e
async def test_e2e_2_restart_daily_loss_preserved() -> None:
    """Pérdida diaria realizada → restart → mismo día: daily_loss preservado y BUY bloqueado."""
    n = 18
    split = 17  # tras el SELL perdedor; el BUY de la vela 17 es el intento bloqueado
    actions = [Action.HOLD] * _WARMUP + [Action.BUY, Action.SELL, Action.BUY]
    closes = [100.0] * _WARMUP + [100.0, 90.0, 90.0]
    candles = [_candle(i, closes[i]) for i in range(n)]

    control = _runner("ctrl", actions, _daily_loss_engine, FakeEventRepo(), FakeCandleRepo())
    for candle in candles:
        await control.handle_candle(SYMBOL, TF, candle)
    assert control._engine.daily_loss_active is True

    repo = FakeEventRepo()
    crepo = FakeCandleRepo()
    live = _runner("restart", actions, _daily_loss_engine, repo, crepo)
    for candle in candles[:split]:
        await live.handle_candle(SYMBOL, TF, candle)
    assert live._engine.daily_loss_active is True
    assert live._engine.realized_pnl_today < 0

    restored = _runner("restart", actions, _daily_loss_engine, repo, crepo)
    restored.replay(
        [(SYMBOL, TF.label, c) for c in candles[:split]], {_event_key(e): e for e in repo.events}
    )
    assert restored._engine.realized_pnl_today == pytest.approx(live._engine.realized_pnl_today)
    assert restored._engine.daily_loss_active is True

    blocked = await restored.handle_candle(SYMBOL, TF, candles[split])
    assert blocked is not None
    assert blocked.filled is False
    assert blocked.action == "BUY"
    assert blocked.risk_reason == "max_daily_loss"

    _assert_state_equal(_state(restored._engine), _state(control._engine))


@pytest.mark.e2e
async def test_e2e_3_4_market_evidence_and_no_lookahead() -> None:
    """Velas + decision_context persistidos; recompute(T) == snapshot(T) (no-lookahead)."""
    n = 60
    candles = [_candle(i, 100.0 + i * 0.5) for i in range(n)]
    repo = FakeEventRepo()
    crepo = FakeCandleRepo()
    runner = PaperRunner(config=_config("audit"), event_repo=repo, candle_repo=crepo)
    for candle in candles:
        await runner.handle_candle(SYMBOL, TF, candle)

    events = repo.events
    assert len(events) == n
    assert all(e.decision_context is not None for e in events)

    persisted = await crepo.session_range("audit", SYMBOL, TF, 0, 2**63 - 1)
    assert [c.timestamp_ms for c in persisted] == [c.timestamp_ms for c in candles]

    recomputed = recompute_decision_contexts(candles)
    for event, expected in zip(events, recomputed, strict=True):
        assert event.decision_context is not None
        assert DecisionContext.from_dict(event.decision_context) == expected


@pytest.mark.e2e
async def test_e2e_5_required_metrics_after_full_run() -> None:
    """Las 7 familias de métricas requeridas (§8) están presentes tras una corrida."""
    from infrastructure.observability.metrics import SetaMetrics

    metrics = SetaMetrics()
    repo = FakeEventRepo()
    crepo = FakeCandleRepo()
    runner = PaperRunner(config=_config("metrics"), event_repo=repo, candle_repo=crepo)
    for i in range(_WARMUP + 1):
        await runner.handle_candle(SYMBOL, TF, _candle(i, 100.0 + i * 0.1))
        metrics.inc_candle()
        metrics.set_atr_ready(runner.atr_ready)
    metrics.set_connected(True)
    metrics.inc_error("ws")
    metrics.inc_reconnect()
    metrics.inc_stale()
    metrics.set_llm_cost(0.01)

    text = metrics.render()
    required = (
        "seta_ws_status",
        "seta_reconnects_total",
        'seta_errors_total{kind="ws"}',
        "seta_ws_stale_total",
        "seta_candles_processed_total",
        "seta_atr_ready",
        "seta_llm_cost_usd",
    )
    for family in required:
        assert family in text, f"métrica faltante: {family}"
    assert f"seta_candles_processed_total {_WARMUP + 1}.0" in text
    assert "seta_atr_ready 1.0" in text


@pytest.mark.e2e
@pytest.mark.parametrize("gap", [0, 1, 3])
async def test_e2e_6_7_8_restart_gap_recovery_parity(gap: int) -> None:
    """Restart con gap de 0/1/N velas: backfill recupera y el estado final == control."""
    n = 30
    split = 10
    gap_end = split + gap
    actions = (
        [Action.HOLD] * _WARMUP + [Action.BUY] + [Action.HOLD] * (n - _WARMUP - 2) + [Action.SELL]
    )
    closes = [100.0 + min(i, 20) * 0.5 for i in range(n)]
    candles = [_candle(i, closes[i]) for i in range(n)]

    control = _runner("ctrl", actions, _default_engine, FakeEventRepo(), FakeCandleRepo())
    for candle in candles:
        await control.handle_candle(SYMBOL, TF, candle)

    repo = FakeEventRepo()
    crepo = FakeCandleRepo()
    live = _runner("restart", actions, _default_engine, repo, crepo)
    for candle in candles[:split]:
        await live.handle_candle(SYMBOL, TF, candle)

    restored = _runner("restart", actions, _default_engine, repo, crepo)
    restored.replay(
        [(SYMBOL, TF.label, c) for c in candles[:split]], {_event_key(e): e for e in repo.events}
    )

    client = FakeClient(candles[split:gap_end])
    svc = BackfillService(client, crepo)
    result = await svc.backfill(
        session_id="restart",
        symbol=SYMBOL,
        timeframe=TF,
        cutoff_ms=gap_end * TF_MS,
        runner=restored,
    )
    assert result.recovered == gap

    for candle in candles[gap_end:]:
        await restored.handle_candle(SYMBOL, TF, candle)

    _assert_state_equal(_state(restored._engine), _state(control._engine))
    assert len(repo.events) == n  # sin pérdida ni duplicado


@pytest.mark.e2e
async def test_e2e_9_reprocess_overlap_is_idempotent() -> None:
    """Vela reentregada (solapamiento REST/WS) no duplica evento ni vela."""
    repo = FakeEventRepo()
    crepo = FakeCandleRepo()
    runner = PaperRunner(config=_config("overlap"), event_repo=repo, candle_repo=crepo)
    candle = _candle(0, 100.0)

    await runner.handle_candle(SYMBOL, TF, candle)
    await runner.handle_candle(SYMBOL, TF, candle)

    assert len(repo.events) == 1
    assert len(await crepo.session_range("overlap", SYMBOL, TF, 0, TF_MS)) == 1


@pytest.mark.e2e
async def test_e2e_10_crash_before_commit_recovers_via_backfill() -> None:
    """La vela no committeada (crash) se recupera por backfill; la committeada no se reinserta."""
    n = 12
    split = 5  # velas 0..4 durables; la vela 5 "se pierde" antes del commit
    actions = [Action.HOLD] * _WARMUP + [Action.BUY] + [Action.HOLD] * (n - _WARMUP - 1)
    closes = [100.0] * _WARMUP + [100.0] + [100.5] * (n - _WARMUP - 1)
    candles = [_candle(i, closes[i]) for i in range(n)]

    repo = FakeEventRepo()
    crepo = FakeCandleRepo()
    live = _runner("crash", actions, _default_engine, repo, crepo)
    for candle in candles[:split]:
        await live.handle_candle(SYMBOL, TF, candle)
    assert len(repo.events) == split

    # Crash: las velas split..split+1 nunca se committean (no están en los repos).
    restored = _runner("crash", actions, _default_engine, repo, crepo)
    restored.replay(
        [(SYMBOL, TF.label, c) for c in candles[:split]], {_event_key(e): e for e in repo.events}
    )

    client = FakeClient(candles[split : split + 2])
    svc = BackfillService(client, crepo)
    result = await svc.backfill(
        session_id="crash",
        symbol=SYMBOL,
        timeframe=TF,
        cutoff_ms=(split + 2) * TF_MS,
        runner=restored,
    )
    assert result.recovered == 2  # el backfill regenera exactamente las velas perdidas

    for candle in candles[split + 2 :]:
        await restored.handle_candle(SYMBOL, TF, candle)

    assert len(repo.events) == n  # sin duplicados ni pérdidas


@pytest.mark.e2e
async def test_e2e_kill_switch_survives_restart_and_blocks_buy() -> None:
    """El kill switch (estado humano no derivable) se restaura y bloquea BUY."""
    system = FakeSystemState(
        {
            KILL_SWITCH_KEY: KillSwitchState(
                active=True, reason="manual", activated_at_ms=42
            ).to_dict()
        }
    )
    restored = await restore_runner(
        config=_config("ks"),
        event_repo=FakeEventRepo(),
        candle_repo=FakeCandleRepo(),
        system_state_repo=system,
        symbol=SYMBOL,
        timeframe=TF,
    )
    assert restored._engine.kill_switch_state.active is True

    runner = PaperRunner(
        config=_config("ks-blocked"),
        event_repo=FakeEventRepo(),
        strategy=PrecomputedStrategy([Action.HOLD] * _WARMUP + [Action.BUY]),  # type: ignore[arg-type]
        kill_switch=KillSwitch(KillSwitchState(active=True, reason="manual", activated_at_ms=42)),
    )
    event = None
    for i in range(_WARMUP + 1):
        event = await runner.handle_candle(SYMBOL, TF, _candle(i, 100.0))

    assert event is not None
    assert event.action == "BUY"
    assert event.filled is False
    assert event.risk_reason == "kill_switch"

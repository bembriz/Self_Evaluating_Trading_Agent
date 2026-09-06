import json
from pathlib import Path

import pytest

from application.ports.paper_trading import PaperTradeEvent
from application.services.paper_runner import (
    PaperRunner,
    PaperRunnerConfig,
    UnsafePaperModeError,
    summarize_events,
    write_certification_state,
    write_periodic_report,
)
from domain.market.candle import Candle, Timeframe
from domain.market.regime import MarketRegime
from domain.market.stream import KlineUpdate
from domain.trading.signal import Action, Signal


def _safe_config() -> PaperRunnerConfig:
    return PaperRunnerConfig(
        trading_mode="paper",
        live_trading_enabled=False,
        symbols=("ETHUSDT",),
        timeframe="15m",
        session_id="paper-baseline-test",
    )


def _paper_event(
    *,
    action: str = "HOLD",
    filled: bool = False,
    fee: float = 0.0,
    slippage_cost: float = 0.0,
    equity: float = 1000.0,
) -> PaperTradeEvent:
    return PaperTradeEvent(
        session_id="paper-baseline-test",
        strategy_version="ema-rsi-baseline-v1",
        strategy_hash="abc123",
        decision_source="baseline",
        symbol="ETHUSDT",
        timeframe="15m",
        timestamp_ms=1_000,
        action=action,
        filled=filled,
        risk_reason="",
        exit_reason="",
        exec_price=100.0 if filled else None,
        quantity=0.1 if filled else None,
        fee=fee,
        slippage_cost=slippage_cost,
        equity=equity,
        kill_switch_active=False,
    )


def _regime_evidence(name: str) -> dict[str, object]:
    return {
        "name": name,
        "symbol": "ETHUSDT",
        "timeframe": "15m",
        "first_seen_at_ms": 1_000,
        "confirmed_at_ms": 3_000,
        "last_seen_at_ms": 3_000,
        "classifier_version": "regime-v1",
        "confirmation_candles": 3,
    }


def test_paper_runner_config_rejects_live_enabled() -> None:
    with pytest.raises(UnsafePaperModeError, match="LIVE_TRADING_ENABLED"):
        PaperRunnerConfig(
            trading_mode="paper",
            live_trading_enabled=True,
            symbols=("ETHUSDT",),
            timeframe="15m",
            session_id="paper-baseline-test",
        ).validate_safe()


def test_paper_runner_config_rejects_non_paper_mode() -> None:
    with pytest.raises(UnsafePaperModeError, match="TRADING_MODE"):
        PaperRunnerConfig(
            trading_mode="backtest",
            live_trading_enabled=False,
            symbols=("ETHUSDT",),
            timeframe="15m",
            session_id="paper-baseline-test",
        ).validate_safe()


class FakePaperTradeRepo:
    def __init__(self) -> None:
        self.events: list[PaperTradeEvent] = []

    async def add(self, event: PaperTradeEvent) -> None:
        self.events.append(event)

    async def list_session(self, session_id: str) -> list[PaperTradeEvent]:
        return [event for event in self.events if event.session_id == session_id]


class FixedRegimeClassifier:
    def __init__(self, regime: MarketRegime) -> None:
        self.regime = regime
        self.calls = 0

    def classify(self, candles: object) -> MarketRegime:
        self.calls += 1
        return self.regime


def _confirmed_kline(timestamp_ms: int) -> KlineUpdate:
    return KlineUpdate(
        "ETHUSDT",
        Timeframe.M15,
        timestamp_ms,
        100.0,
        101.0,
        99.0,
        100.5,
        10.0,
        1005.0,
        True,
    )


async def test_runner_ignores_unconfirmed_kline() -> None:
    repo = FakePaperTradeRepo()
    runner = PaperRunner(config=_safe_config(), event_repo=repo)
    kline = KlineUpdate("ETHUSDT", Timeframe.M15, 1_000, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, False)

    event = await runner.handle_kline(kline)

    assert event is None
    assert repo.events == []


async def test_runner_persists_event_for_confirmed_kline() -> None:
    repo = FakePaperTradeRepo()
    runner = PaperRunner(config=_safe_config(), event_repo=repo)
    kline = KlineUpdate(
        "ETHUSDT", Timeframe.M15, 1_000, 100.0, 101.0, 99.0, 100.5, 10.0, 1005.0, True
    )

    event = await runner.handle_kline(kline)

    assert event is not None
    assert repo.events == [event]
    assert event.session_id == "paper-baseline-test"
    assert event.decision_source == "baseline"
    assert event.symbol == "ETHUSDT"
    assert event.timeframe == "15m"
    assert event.timestamp_ms == 1_000
    assert event.action in {"BUY", "SELL", "HOLD"}
    assert event.equity > 0.0


async def test_runner_confirms_regime_only_after_three_confirmed_candles() -> None:
    repo = FakePaperTradeRepo()
    classifier = FixedRegimeClassifier(MarketRegime.SIDEWAYS)
    runner = PaperRunner(
        config=_safe_config(),
        event_repo=repo,
        regime_classifier=classifier,  # type: ignore[arg-type]
    )

    for timestamp_ms in (1_000, 2_000, 3_000):
        await runner.handle_kline(_confirmed_kline(timestamp_ms))

    assert [item["name"] for item in runner.regime_evidence()] == ["SIDEWAYS"]
    assert classifier.calls == 3


async def test_runner_does_not_classify_an_incomplete_candle() -> None:
    repo = FakePaperTradeRepo()
    classifier = FixedRegimeClassifier(MarketRegime.SIDEWAYS)
    runner = PaperRunner(
        config=_safe_config(),
        event_repo=repo,
        regime_classifier=classifier,  # type: ignore[arg-type]
    )
    kline = KlineUpdate("ETHUSDT", Timeframe.M15, 1_000, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, False)

    await runner.handle_kline(kline)

    assert classifier.calls == 0
    assert runner.regime_evidence() == []


async def test_runner_run_once_is_safe_noop_until_stream_adapter_is_wired() -> None:
    repo = FakePaperTradeRepo()
    runner = PaperRunner(config=_safe_config(), event_repo=repo)

    await runner.run_once()

    assert repo.events == []


def test_summarize_events_counts_decisions_and_fills() -> None:
    events = [
        _paper_event(action="BUY", filled=True, fee=0.10, slippage_cost=0.02, equity=999.88),
        _paper_event(action="HOLD", filled=False, fee=0.0, slippage_cost=0.0, equity=999.88),
    ]

    summary = summarize_events(events)

    assert summary.decisions == {"BUY": 1, "SELL": 0, "HOLD": 1}
    assert summary.fills == 1
    assert summary.fees == 0.10
    assert summary.slippage == 0.02
    assert summary.latest_equity == 999.88


def test_write_periodic_report_contains_certification_progress(tmp_path: Path) -> None:
    summary = summarize_events([_paper_event(action="BUY", filled=True)])
    report = tmp_path / "paper-report.md"

    write_periodic_report(summary, report)

    text = report.read_text(encoding="utf-8")
    assert "# Paper Trading Periodic Report" in text
    assert "decision_source: baseline" in text
    assert "fills: 1" in text


def test_write_certification_state_keeps_pending_thresholds_honest(tmp_path: Path) -> None:
    state_path = tmp_path / "certification-state.json"
    report_path = tmp_path / "paper-report.md"
    report_path.write_text("# Paper report\n", encoding="utf-8")
    summary = summarize_events([_paper_event(action="BUY", filled=True)])

    write_certification_state(
        summary,
        state_path,
        previous={},
        regime_evidence=[],
        report_path=report_path,
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["strategy_hash"] == "abc123"
    assert state["active_strategy_hash"] == "abc123"
    assert state["trade_count"] == 1
    assert state["calendar_days"] == 1
    assert state["market_regimes"] == []
    assert state["periodic_reports"] == [str(report_path)]


def test_summarize_events_computes_pnl_from_initial_equity() -> None:
    events = [
        _paper_event(action="BUY", filled=True, fee=0.10, slippage_cost=0.02, equity=1100.0),
    ]

    summary = summarize_events(events, initial_equity=1000.0)

    assert summary.initial_equity == 1000.0
    assert summary.pnl_absolute == 100.0
    assert summary.pnl_pct == pytest.approx(0.10)
    assert summary.delta_fills is None


def test_summarize_events_delta_with_previous() -> None:
    previous = summarize_events(
        [_paper_event(action="HOLD", filled=False, equity=1050.0)],
        initial_equity=1000.0,
    )
    events = [
        _paper_event(action="HOLD", filled=False, equity=1050.0),
        _paper_event(action="BUY", filled=True, equity=1100.0),
    ]

    summary = summarize_events(events, previous=previous, initial_equity=1000.0)

    assert summary.delta_fills == 1
    assert summary.delta_decisions == {"BUY": 1, "SELL": 0, "HOLD": 0}
    assert summary.delta_pnl_absolute == 50.0
    assert summary.delta_pnl_pct == pytest.approx(0.05)


def test_write_periodic_report_includes_pnl_and_delta(tmp_path: Path) -> None:
    summary = summarize_events(
        [_paper_event(action="BUY", filled=True, equity=1100.0)],
        initial_equity=1000.0,
    )
    report = tmp_path / "paper-report.md"

    write_periodic_report(summary, report)

    text = report.read_text(encoding="utf-8")
    assert "pnl_absolute: 100.0" in text
    assert "pnl_pct: 0.1" in text
    assert "delta_fills: n/a" in text


def test_write_periodic_report_includes_regime_review_telemetry(tmp_path: Path) -> None:
    summary = summarize_events([_paper_event(action="HOLD")])
    report = tmp_path / "paper-report.md"

    write_periodic_report(
        summary,
        report,
        regime_evidence=[_regime_evidence("SIDEWAYS")],
        rejected_regime_candidates=1,
    )

    text = report.read_text(encoding="utf-8")
    assert "regime_confirmation_candles: 3" in text
    assert "regime_classifier_version: regime-v1" in text
    assert "rejected_regime_candidates: 1" in text


def test_write_certification_state_preserves_only_existing_periodic_reports(
    tmp_path: Path,
) -> None:
    existing_report = tmp_path / "paper-report.md"
    existing_report.write_text("# Paper report\n", encoding="utf-8")
    missing_report = tmp_path / "missing-report.md"
    state_path = tmp_path / "certification-state.json"
    summary = summarize_events([_paper_event(action="BUY", filled=True)])

    write_certification_state(
        summary,
        state_path,
        previous={"periodic_reports": [str(existing_report), str(missing_report)]},
        regime_evidence=[],
        report_path=existing_report,
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["periodic_reports"] == [str(existing_report)]


def test_write_certification_state_merges_existing_and_new_regime_evidence(tmp_path: Path) -> None:
    state_path = tmp_path / "certification-state.json"
    report_path = tmp_path / "paper-report.md"
    report_path.write_text("# Paper report\n", encoding="utf-8")
    summary = summarize_events([_paper_event(action="BUY", filled=True)])

    write_certification_state(
        summary,
        state_path,
        previous={"market_regimes": [_regime_evidence("SIDEWAYS")], "periodic_reports": []},
        regime_evidence=[_regime_evidence("TREND_UP")],
        report_path=report_path,
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert [item["name"] for item in state["market_regimes"]] == ["SIDEWAYS", "TREND_UP"]
    assert state["periodic_reports"] == [str(report_path)]


class AlwaysBuyStrategy:
    version = "test-always-buy-v1"

    def on_candle(self, candle: Candle) -> Signal:
        return Signal(timestamp_ms=candle.timestamp_ms, action=Action.BUY, reason="test")


async def test_runner_rechaza_buy_por_stop_unavailable_solo_durante_warmup_atr() -> None:
    repo = FakePaperTradeRepo()
    runner = PaperRunner(
        config=_safe_config(),
        event_repo=repo,
        strategy=AlwaysBuyStrategy(),  # type: ignore[arg-type]
    )

    event = await runner.handle_kline(_confirmed_kline(1_000))

    assert event is not None
    assert event.action == "BUY"
    assert event.filled is False
    assert event.risk_reason == "stop_unavailable"


async def test_runner_llena_buy_cuando_el_atr_esta_disponible() -> None:
    repo = FakePaperTradeRepo()
    runner = PaperRunner(
        config=_safe_config(),
        event_repo=repo,
        strategy=AlwaysBuyStrategy(),  # type: ignore[arg-type]
    )

    event = None
    for i in range(15):
        event = await runner.handle_kline(_confirmed_kline(1_000 + i * 900_000))

    assert event is not None
    assert event.action == "BUY"
    assert event.filled is True
    assert event.risk_reason == ""
    assert event.quantity is not None and event.quantity > 0
    assert event.exec_price is not None


async def test_runner_no_alimenta_atr_con_velas_no_confirmadas() -> None:
    repo = FakePaperTradeRepo()
    runner = PaperRunner(
        config=_safe_config(),
        event_repo=repo,
        strategy=AlwaysBuyStrategy(),  # type: ignore[arg-type]
    )
    for i in range(20):
        kline = KlineUpdate(
            "ETHUSDT", Timeframe.M15, 1_000 + i * 900_000, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, False
        )
        assert await runner.handle_kline(kline) is None

    event = await runner.handle_kline(_confirmed_kline(1_000 + 20 * 900_000))

    assert event is not None
    assert event.risk_reason == "stop_unavailable"


async def test_runner_atr_ready_flips_after_warmup() -> None:
    repo = FakePaperTradeRepo()
    runner = PaperRunner(
        config=_safe_config(),
        event_repo=repo,
        strategy=AlwaysBuyStrategy(),  # type: ignore[arg-type]
    )

    assert runner.atr_ready is False
    for i in range(14):
        await runner.handle_kline(_confirmed_kline(1_000 + i * 900_000))
    assert runner.atr_ready is False  # 1 prev_close + 13 TR
    await runner.handle_kline(_confirmed_kline(1_000 + 14 * 900_000))
    assert runner.atr_ready is True  # 15ª vela completa el warmup ATR
